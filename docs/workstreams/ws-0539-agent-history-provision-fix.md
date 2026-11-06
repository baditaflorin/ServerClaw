# WS-0539: Do not cut the agent-history guest's first boot off

## Status

In progress. The pull request is open and not merged; nothing is applied. No `[live-apply]` marker.

## Goal

The first provisioning of VM 155 (2026-10-29) lost data: the per-guest play hard-stopped the VM seconds after the guests role started it, to apply the balloon and discard settings. That cut cloud-init's first boot off and left zero-byte netplan, ssh host keys and apt lists plus a saved instance-id, so the next boot never configured the network. A second defect hid behind it: cloud-init installed `docker.io` while the docker_runtime role converges Docker CE and removes `docker.io` as a conflicting package, which ended every new cloud-init instance of this guest in status error and tripped the play's own `cloud-init status --wait`.

## Change

- `playbooks/agent-history-vm.yml`: the Proxmox play no longer stops or restarts the VM (the balloon floor is applied live; the data disk's `discard=on` stays pending). The guest play waits for SSH and `cloud-init status --wait`, then reads `qm config` and `qm config --current 1`; only when they differ (hardware settings pending) does it run one graceful `qm shutdown --timeout 600 --forceStop 1` and `qm start`, wait for SSH and cloud-init again, and go on. A re-run with nothing pending restarts nothing.
- `inventory/host_vars/proxmox-host.yml`: `docker.io` is removed from the agent-history guest's `packages` (the other guests are untouched).
- `tests/test_agent_history_vm_playbook.py`: six static guards (no `qm stop` anywhere, the Proxmox play does not restart the VM, the restart comes after the cloud-init wait and is graceful, only on pending changes, followed by a wait, no `docker.io`); mutation-checked against a forced stop and a non-graceful shutdown.

Not exercised against a live VM: the guest already exists, and this play is not run again by this change. The restart branch is covered by the static tests and `ansible-syntax` only.
