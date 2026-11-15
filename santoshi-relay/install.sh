#!/bin/bash
# santoshi-relay/install.sh: the Santoshi live relay on chromium-vm (Marko, 14.11.2026: "I just want to send one stream, and then it is
# relayed somewhere"). Run on the VM from the repo checkout:  sudo santoshi-relay/install.sh  (the publish key's hash on stdin the
# first time: printf 'sha256:...' | sudo santoshi-relay/install.sh; the key itself is fed by the Mac: sudo tee /etc/santoshi-relay/key)
# Installs MediaMTX (pinned, sha256 checked), its own system user, the TLS certificate (Let's Encrypt, HTTP-01 on port 80 only while
# certbot runs), the firewall lines, the units, and the registry entry (core). Safe to run again.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
cd "$(dirname "$0")/.."
VER=v1.21.3
SHA=27f038237cb5f77a724f6afc58eca2798f2bc4edf9989895631a80eeb41a4fe2   # mediamtx_v1.21.3_linux_arm64.tar.gz (release digest)
HOST=relay.ples-duse.org
L=/usr/local/lib/chromium-vm

echo "== MediaMTX $VER"
id mediamtx >/dev/null 2>&1 || useradd --system --home /srv/santoshi-rec --shell /usr/sbin/nologin mediamtx
if [ ! -x /opt/mediamtx/$VER/mediamtx ]; then
  T=$(mktemp -d); curl -fsSL -o "$T/m.tgz" "https://github.com/bluenviron/mediamtx/releases/download/$VER/mediamtx_${VER}_linux_arm64.tar.gz"
  echo "$SHA  $T/m.tgz" | sha256sum -c -
  install -d /opt/mediamtx/$VER; tar -xzf "$T/m.tgz" -C /opt/mediamtx/$VER mediamtx LICENSE; rm -rf "$T"
fi
ln -sfn /opt/mediamtx/$VER /opt/mediamtx/current

echo "== recordings: /srv/santoshi-rec (mediamtx writes, ubuntu uploads)"
install -d -m 2775 -o mediamtx -g ubuntu /srv/santoshi-rec /srv/santoshi-rec/santoshi
usermod -aG mediamtx ubuntu

echo "== config"
install -d -m 750 -o root -g mediamtx /etc/mediamtx
if [ ! -s /etc/mediamtx/publish.hash ]; then
  read -r H; [[ "$H" == sha256:* ]] || { echo "give the publish key's hash on stdin (sha256:...)" >&2; exit 1; }
  printf '%s\n' "$H" > /etc/mediamtx/publish.hash; chmod 640 /etc/mediamtx/publish.hash; chgrp mediamtx /etc/mediamtx/publish.hash
fi
H=$(cat /etc/mediamtx/publish.hash)
# 15.11.2026 "mixer only": the CLOUD MIXER's own key (user mixer, the only publisher on santoshi); made here if missing
if [ ! -s /etc/santoshi-relay/mixer-key ]; then
  install -d -m 750 -o root -g ubuntu /etc/santoshi-relay
  ( umask 027; head -c 24 /dev/urandom | base64 | tr -d '/+=' > /etc/santoshi-relay/mixer-key ); chown root:ubuntu /etc/santoshi-relay/mixer-key
fi
MH="sha256:$(tr -d '\n' < /etc/santoshi-relay/mixer-key | openssl dgst -binary -sha256 | base64)"
sed -e "s|@PUBLISH_HASH@|$H|" -e "s|@MIXER_HASH@|$MH|" santoshi-relay/mediamtx.yml.in > /etc/mediamtx/mediamtx.yml
chown root:mediamtx /etc/mediamtx/mediamtx.yml; chmod 640 /etc/mediamtx/mediamtx.yml
install -d -m 750 -o root -g ubuntu /etc/santoshi-relay
[ -f /etc/santoshi-relay/key ] || { touch /etc/santoshi-relay/key; chown root:ubuntu /etc/santoshi-relay/key; chmod 640 /etc/santoshi-relay/key; }
install -m 755 santoshi-relay/santoshi-forward $L/santoshi-forward

echo "== TLS for $HOST"
command -v certbot >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -q certbot >/dev/null
install -m 755 santoshi-relay/certbot-deploy-hook /etc/letsencrypt/renewal-hooks/deploy/santoshi-relay 2>/dev/null || {
  install -d /etc/letsencrypt/renewal-hooks/deploy; install -m 755 santoshi-relay/certbot-deploy-hook /etc/letsencrypt/renewal-hooks/deploy/santoshi-relay; }
iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || iptables -I INPUT 2 -p tcp --dport 80 -j ACCEPT
[ -d /etc/letsencrypt/live/$HOST ] || certbot certonly --standalone -n --agree-tos --register-unsafely-without-email -d $HOST
/etc/letsencrypt/renewal-hooks/deploy/santoshi-relay || true

echo "== firewall (Oracle security list has the same ports)"
for r in "tcp 8888" "tcp 8889" "tcp 8443" "tcp 8189" "udp 8189" "udp 8890"; do
  set -- $r; iptables -C INPUT -p $1 --dport $2 -j ACCEPT 2>/dev/null || iptables -I INPUT 2 -p $1 --dport $2 -j ACCEPT
done

echo "== units + registry"
install -m 755 santoshi-relay/santoshi_rec_upload.py $L/santoshi_rec_upload.py
install -m 644 santoshi-relay/systemd/santoshi-relay.service santoshi-relay/systemd/santoshi-rec-upload.service /etc/systemd/system/
install -m 644 tools/vmctl/services.json /etc/chromium-vm/services.json
systemctl daemon-reload
systemctl enable santoshi-relay.service santoshi-rec-upload.service
systemctl restart santoshi-relay.service; sleep 2; systemctl restart santoshi-rec-upload.service
systemctl is-active santoshi-relay.service santoshi-rec-upload.service
curl -s -o /dev/null -w "WHEP door: HTTP %{http_code}\n" -X OPTIONS https://$HOST:8889/santoshi/whep
