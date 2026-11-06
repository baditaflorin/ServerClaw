# WS-20261103: the 0docker tailnet proxy sockets survive a tailscaled restart

## Status

In progress (branch `claude/tailscaled-restart-0docker`). Git only: two hostconf drop-in files with two manifest entries, a 0docker family of variants in the tailscaled-restart rig, a test, and the runbook.
**Nothing is applied** and nothing on the hypervisor was changed (read-only ssh only). The 0mcp half (PR 661) was applied on 2026-11-03 09:06:53Z and live-tested at 09:16:25Z with a controlled `systemctl restart tailscaled` (all 21 sockets active throughout); the 0docker hypervisor has not been tested live. The apply is `scripts/hostconf.py apply --host bastion --file ... --yes` (a `daemon-reload`, no restart) after the
user's yes; the exact commands are in `docs/runbooks/tailscaled-restart-proxies.md`, "0docker hypervisor".

## Goal

Follow-up of `ws-20261102-tailscaled-restart-proxies` (0mcp, PR 661). Its runbook listed two things still exposed on the 0docker hypervisor (`bastion` in `config/hostconf/hostconf.yaml`, host `pve-0docker`, systemd 252):

1. `woodpecker-exec-proxy@.socket` has `BindToDevice=tailscale0` and no `FreeBind`. PR 659 (`ws-20261102-exec-proxy-tailscale0`) made the device `Want` the socket, which fixes the "device was not active" half; the
   device appears before it has its address, so the start it triggers fails with `Cannot assign requested address` (the rig rows `role-wants` of 0mcp, and `docker0-live` here).
2. `zdocker-hypervisor-metrics-proxy.socket` has `FreeBind=true` (it came back at 12:34:59 on 2026-11-02) but is only `WantedBy=sockets.target`: after a separate `stop` and `start` of tailscaled nothing starts it.

## Change

- `config/hostconf/files/socket-free-bind.0docker.conf` and the entry `socket-free-bind.woodpecker-exec-proxy` (`/etc/systemd/system/woodpecker-exec-proxy@.socket.d/20-free-bind.conf`, on the template so every instance has it).
- `config/hostconf/files/tailscale0-wants-zdocker-metrics-proxy.0docker.conf` and the entry `tailscale0-wants-zdocker-metrics-proxy` (`/etc/systemd/system/sys-subsystem-net-devices-tailscale0.device.d/10-wants-zdocker-hypervisor-metrics-proxy.conf`).
  A second drop-in next to PR 659's `10-wants-woodpecker-exec-proxy.conf`: systemd adds up `Wants=`, and PR 659's applied file is not rewritten.
- both ids on the `bastion` file list; README: 89 catalog files.
- `scripts/tailscaled_restart_rig/`: a 0docker family of four variants (an ablation on top of what is live on the hypervisor), modelled on the units read from the host (`0docker-units/` holds the two files of the
  template, the zdocker socket is rendered from the role), with the 0docker address and systemd 252.
- `tests/test_tailscaled_restart_0docker.py`: the inventory, the hostconf catalog and the rig fixtures stay equal.
- `docs/runbooks/tailscaled-restart-proxies.md`: the 0docker section (what the scan found, the apply, the read-only checks, the rollback).
- `build/platform-manifest.json`: regenerated (`scripts/platform_manifest.py --write`); main's copy was already stale (`configure-agent-history` listed 29 steps, the runbook has 33; the only other diff is the generated timestamp), nothing in it comes from this change, and the gate's `schema-validation` failed on it (`manifest is out of date`).

## Not in this change

- The two socat relays `0memory-postgres-relay.service` and `registrant-postgres-relay.service` (`Requires=tailscaled.service`, they listen on the vmbr1 address 10.10.10.1, not the tailnet address): they come back after a restart
  (12:34:59 on 2026-11-02) and after a crash; they stay stopped only after a separate `stop` and `start` of tailscaled. Proposed separately: see the runbook.
- Turning off tailscale's auto-update: the user's decision (runbook of PR 661).

## Verification

`python3 scripts/hostconf.py check`, the hostconf, fleet-observability and tailscaled-restart tests, `systemd-analyze verify` inside the rig, the rig itself on a build host (`RIG OK` on systemd 252 for the 0docker family
and for the 0mcp family), then the repository pre-push gate on the build server. After the apply: `python3 scripts/hostconf.py drift --host bastion`; the first tailscaled restart (or a controlled one) is the live proof.

## Rollback

Remove the two files on the hypervisor and `systemctl daemon-reload`, or revert the commit and apply again.
