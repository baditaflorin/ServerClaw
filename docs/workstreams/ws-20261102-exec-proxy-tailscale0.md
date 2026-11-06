# WS-20261102: tailscale0 Wants the Woodpecker exec-proxy socket

## Status

In review (branch `claude/hostconf-exec-proxy-tailscale0`). A tool change (device-unit drop-ins), one drop-in file, the manifest entry and documentation. Nothing is applied yet: the apply is `scripts/hostconf.py apply --host bastion --file woodpecker-exec-proxy-follows-tailscale0 --yes` (a `daemon-reload`, no restart).

## Goal

On 2026-11-02 from 11:33Z to 12:44Z the whole Woodpecker CI plane (`ci.0exec.com`) stood still: every agent was refused on `100.64.0.5:9000`, the 0docker hypervisor's tailnet address, where
`woodpecker-exec-proxy@9000.socket` relays the agents to the server's gRPC port in CT108. The socket listens with `BindToDevice=tailscale0`, so systemd stops it when the device goes away; the
automatic start at 12:34:59 CET failed (`Bound to unit sys-subsystem-net-devices-tailscale0.device, but unit isn't active`) and nothing started it again. The web API stayed up, so the plane looked
alive (91 pipelines pending, 1 of 31 agents online). It was started by hand at 12:44Z. What made tailscale0 flap at 11:33Z was not found.

## Change

- `config/hostconf/files/woodpecker-exec-proxy-follows-tailscale0.0docker.conf`: `[Unit] Wants=woodpecker-exec-proxy@9000.socket`.
- `config/hostconf/hostconf.yaml`: entry `woodpecker-exec-proxy-follows-tailscale0` (destination `/etc/systemd/system/sys-subsystem-net-devices-tailscale0.device.d/10-wants-woodpecker-exec-proxy.conf`,
  expect `systemctl show sys-subsystem-net-devices-tailscale0.device -p Wants` = the socket) and the entry in the `bastion` file list.
- `scripts/hostconf.py`: `UNIT_TYPES` gains `device`, so a drop-in of a device unit is a path the tool may write. Nothing else about what it may touch changes.
- `tests/test_hostconf.py`: the new destination is a `systemd_dropin`.
- `config/hostconf/README.md`: 66 catalog files, and the drop-in row names device units.

## Verified (2026-11-02, the hypervisor, systemd 252)

A dummy interface `dumtest0`, a drop-in `Wants=` of a test unit on its device unit, a test unit bound to the device: with the device up and the unit inactive, `daemon-reload` does not start it;
removing the device and adding it back started the unit by itself ("device back, service: active"). Everything was under `/run` and removed afterwards (the dummy link, the drop-in and the unit are gone;
`woodpecker-exec-proxy@9000.socket` stayed active throughout).

## Not in this change

- No alert for "agents online far below registered while pipelines wait": no metric for it exists yet (`woodpecker_agents_unnamed` is the only agent-record metric).
- No watchdog timer: hostconf writes drop-ins only. The device `Wants=` covers the flap that happened; a socket that stops for another reason is not restarted by this.

## Verification

`python3 scripts/hostconf.py check` (42 hosts, 66 files), the hostconf tests (179 passed), then the repository pre-push gate on the build server and, after the apply, `python3 scripts/hostconf.py drift --host bastion`.

## Rollback

Remove the drop-in on the hypervisor and `systemctl daemon-reload`, or revert the commit and apply again.
