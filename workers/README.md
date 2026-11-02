# Workers on chromium-vm

Marko, 2.11.2026: *"let's start our adventure in creating different workers for our virtual environment"*. A worker
is a small program on the VM that does a job on its own, with no session connected: its task list is on Google Drive,
its results are written next to what it makes, and it runs as a systemd service that survives reboots.

| worker | service | the task list | the results |
|---|---|---|---|
| gemini-images | chromium-vm-worker-gemini | Drive: Chromium Downloads/Gemini/_batch/batch.json + refs/ | the pictures and RESULTS.txt in the batch's folder (Gemini/life-story) |

Install one: copy the repo to the VM (`tar | ssh`), then
`sudo install -D -m 755 workers/<w>/<w>.py /usr/local/lib/chromium-vm/workers/`, the .service into
/etc/systemd/system (with @VM_USER@ → ubuntu), `systemctl enable --now`. Logs: ~/.config/chromium-vm/workers/<w>/.
