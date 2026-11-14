#!/usr/bin/env python3
"""vmctl_client: start, stop and lease chromium-vm's services from any program (Mac, cloud session with Tailscale,
the VM itself). One file, standard library only: copy it or put its folder on sys.path.

    from vmctl_client import VM
    vm = VM()                                   # URL and token found by themselves (below)
    vm.services()                               # [{name, short, title, kind, core, running, manual, leases}]
    vm.running('pixel1')                        # True / False
    vm.start('chrome'); vm.stop('chrome')       # core services refuse stop (HTTP 403)
    with vm.using('pixel1', minutes=30, who='my-tests'):
        ...                                     # started if needed and held; when the block ends the lease is released,
                                                # and the service stops if the lease started it and nobody else holds it
    l = vm.lease('firefox', 20, who='ttt'); vm.renew(l['id'], 20); vm.release(l['id'])
    vm.ensure('pixel-door', minutes=30, who='pixel7')    # start + lease, returns the lease (it ends by itself)

Command line:  vmctl_client.py list | start NAME [--gui] | stop NAME | restart NAME | lease NAME MIN [WHO] |
               ensure NAME [MIN] [WHO] | release ID | leases | log
URL:   $VMCTL_URL, else http://100.102.86.30:8896 (chromium-vm on Tailscale).
Token: $VMCTL_TOKEN, else the first file that exists of $VMCTL_TOKEN_FILE, ~/Downloads/API/chromium-vm-vmctl.txt (Mac),
       ~/.config/chromium-vm/vmctl-token (the VM). Never printed.
"""
import contextlib, json, os, sys, urllib.error, urllib.request

DEFAULT_URL = 'http://100.102.86.30:8896'
TOKEN_FILES = [os.environ.get('VMCTL_TOKEN_FILE', ''), '~/Downloads/API/chromium-vm-vmctl.txt', '~/.config/chromium-vm/vmctl-token']


class VMError(RuntimeError):
    def __init__(self, status, msg):
        super().__init__(f'{status}: {msg}'); self.status = status


class VM:
    def __init__(self, url=None, token=None, timeout=330, who=None):
        self.url = (url or os.environ.get('VMCTL_URL') or DEFAULT_URL).rstrip('/')
        self.timeout = timeout                     # a Pixel takes ~40 s to boot; Chrome a few seconds
        self.who = who or os.environ.get('VMCTL_WHO') or os.path.basename(sys.argv[0] or 'python')
        self._token = token or os.environ.get('VMCTL_TOKEN')
        if not self._token:
            for f in TOKEN_FILES:
                p = os.path.expanduser(f) if f else ''
                if p and os.path.exists(p):
                    self._token = open(p).read().strip(); break
        if not self._token:
            raise VMError(0, 'no vmctl token (set VMCTL_TOKEN or put it in ~/Downloads/API/chromium-vm-vmctl.txt)')

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else (b'{}' if method == 'POST' else None)
        r = urllib.request.Request(self.url + path, data=data, method=method,
                                   headers={'X-Mantra-Token': self._token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(r, timeout=self.timeout) as resp:
                out = json.load(resp)
        except urllib.error.HTTPError as e:
            try: msg = json.load(e).get('error', e.reason)
            except Exception: msg = e.reason
            raise VMError(e.code, msg) from None
        except urllib.error.URLError as e:
            raise VMError(0, f'vmctl not reachable at {self.url} ({e.reason})') from None
        return out

    def health(self):
        return self._call('GET', '/health')

    def services(self):
        return self._call('GET', '/services')['services']

    def status(self, name):
        return self._call('GET', f'/services/{name}')['service']

    def running(self, name):
        return bool(self.status(name)['running'])

    def start(self, name, gui=False):
        return self._call('POST', f'/services/{name}/start', {'who': self.who, 'gui': gui})['result']

    def stop(self, name):
        return self._call('POST', f'/services/{name}/stop', {'who': self.who})['result']

    def restart(self, name, gui=False):
        return self._call('POST', f'/services/{name}/restart', {'who': self.who, 'gui': gui})['result']

    def lease(self, name, minutes=30, who=None, gui=False):
        return self._call('POST', f'/services/{name}/lease', {'minutes': minutes, 'who': who or self.who, 'gui': gui})['result']

    ensure = lease                                  # "I need NAME for MIN minutes"

    def renew(self, lease_id, minutes=30):
        return self._call('POST', f'/leases/{lease_id}/renew', {'minutes': minutes, 'who': self.who})['result']

    def release(self, lease_id):
        return self._call('POST', f'/leases/{lease_id}/release', {'who': self.who})['result']

    def leases(self):
        return self._call('GET', '/leases')['leases']

    def log(self):
        return self._call('GET', '/log')['log']

    @contextlib.contextmanager
    def using(self, name, minutes=30, who=None, gui=False):
        l = self.lease(name, minutes, who, gui)
        try:
            yield l
        finally:
            with contextlib.suppress(VMError):
                self.release(l['id'])


def main(a):
    if not a or a[0] in ('-h', '--help'): print(__doc__); return 0
    vm = VM(); c, r = a[0], a[1:]
    try:
        if c == 'list':
            for s in vm.services():
                print(f"{'●' if s['running'] else '○'} {s['name']:<15} {s['short']:<8} {'CORE ' if s['core'] else '     '}"
                      f"{'running' if s['running'] else 'stopped'}  {s['title']}")
        elif c == 'start': print(json.dumps(vm.start(r[0], gui='--gui' in r)))
        elif c == 'stop': print(json.dumps(vm.stop(r[0])))
        elif c == 'restart': print(json.dumps(vm.restart(r[0])))
        elif c in ('lease', 'ensure'):
            print(json.dumps(vm.lease(r[0], float(r[1]) if len(r) > 1 else 30, r[2] if len(r) > 2 else None)))
        elif c == 'release': print(json.dumps(vm.release(r[0])))
        elif c == 'leases': print(json.dumps(vm.leases(), indent=1))
        elif c == 'log': print('\n'.join(vm.log()))
        elif c == 'health': print(json.dumps(vm.health()))
        else: print(__doc__); return 2
    except VMError as e:
        print(f'vmctl: {e}', file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
