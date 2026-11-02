# LESSONS

1. (2.11.2026) Oracle Always Free has 200 GB of block storage in all: replace a boot volume at the same size, then grow it.

- 2.11.2026: Ubuntu 24.04 sets kernel.apparmor_restrict_unprivileged_userns=1, so the xtradeb Chromium (.deb) dies
  with "No usable sandbox!" in a loop. Fix: an AppArmor profile for /usr/lib/chromium/chromium with `userns,`
  (stage1/apparmor/chromium-vm, loaded by setup.sh). Never --no-sandbox.
- 2.11.2026: the repo is private and the VM has no GitHub login: copy stage1 over with `tar | ssh`, don't clone.
