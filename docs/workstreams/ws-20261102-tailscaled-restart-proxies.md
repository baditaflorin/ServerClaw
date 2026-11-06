# WS-20261102: the 0mcp tailnet proxy sockets survive a tailscaled restart

## Status

Merged as PR 661 (git: a socket template change, one inventory flag, two hostconf drop-in files with 21 manifest entries, a throwaway-systemd rig, tests and a runbook). **Applied on pve-0mcp on 2026-11-03 09:06:53Z** with `scripts/hostconf.py apply --host pve-0mcp` and the 21 files
(`daemon-reload` only, no unit restarted, hostconf's read-back all ok: the device `Wants` lists 21 sockets, `FreeBind=yes` on all 21, all 21 active, 25 listeners on the tailnet IP, `up{9101}` 1), and **live-tested at 09:16:25Z** with a controlled `systemctl restart tailscaled`: the address was back after 3.46 s,
the listeners after 4 s and all 21 sockets were active in every sample (21 of 21 throughout); only the 19 `lv3-tailscale-proxy-*.service` units showed `failed` ("Didn't get any sockets passed in") until `systemctl reset-failed`. The numbers are in `docs/runbooks/tailscaled-restart-proxies.md`.
The 0docker hypervisor is the follow-up `ws-20261103-tailscaled-restart-0docker`.

## Goal

On 2026-11-02 at 12:33 CET tailscaled on the 0mcp hypervisor updated itself (the Tailscale control plane's client update: `tailscale update --yes`, which ran `apt-get install --yes --allow-downgrades tailscale=1.104.4`),
and was restarted. systemd stopped every socket with `Requires=tailscaled.service` and started them again as soon as tailscaled reported "started", before `tailscale0` existed and 0.8 s before it had its address. The 19
`lv3-tailscale-proxy-*` sockets (`BindToDevice=tailscale0`) failed with `Bound to unit sys-subsystem-net-devices-tailscale0.device, but unit isn't active`, `zmcp-runtime-general-metrics-proxy.socket` with
`Cannot assign requested address`. All 20 stayed dead for 8 hours (OpenBao, Postgres, Vaultwarden, Gitea, Woodpecker, ... ; the alert that showed it was `FleetNodeExporterDown` for runtime-general) until they were started by
hand. `woodpecker-0exec-build-metrics-proxy.socket` has `FreeBind=true` and came back at once. The same self-update ran on the 0docker hypervisor at 12:33:24 CET: it is the "unexplained" tailscale0 flap of
`ws-20261102-exec-proxy-tailscale0`. The weakness returns at every tailscale update and every tailscaled restart.

## Change

- `collections/ansible_collections/lv3/platform/roles/proxmox_tailscale_proxy/templates/lv3-tailscale-proxy.socket.j2`: `FreeBind=true` (next to `BindToDevice=tailscale0`, which stays).
- `inventory/fleet-observability.yml`: `free_bind: true` for `zmcp-runtime-general-metrics-proxy` (the template already renders it; the build-metrics proxy had it since 2026-10-12).
- `config/hostconf/files/socket-free-bind.0mcp.conf` and 20 manifest entries `socket-free-bind.<unit>` (`<unit>.socket.d/20-free-bind.conf`): the zero-restart way to give the running hypervisor the same setting.
- `config/hostconf/files/tailscale0-wants-lv3-proxies.0mcp.conf` and the entry `tailscale0-wants-lv3-proxies`
  (`/etc/systemd/system/sys-subsystem-net-devices-tailscale0.device.d/10-wants-lv3-tailscale-proxies.conf`): `Wants=` of the 19 lv3 sockets and the two node-exporter proxy sockets, so systemd starts them when the device
  comes back. All 21 entries are on the `pve-0mcp` file list; README: 87 catalog files.
- `scripts/tailscaled_restart_rig/`: a privileged systemd container on a build host (`--network none`) that boots the real templates and hostconf files with a stand-in tailscaled with the journal's timing, restarts it four ways and
  reports which sockets stay dead; five variants (an ablation). `tests/test_tailscaled_restart_proxies.py`: the catalog, inventory and hostconf lists stay equal, the rig builds, the runbook names the apply path.
- `docs/runbooks/tailscaled-restart-proxies.md`: the incident, the mechanism, why these two settings and not the alternatives, the rig result, the apply and rollback, the decision about tailscale's auto-update, what
  `pg-replica-tailnet.service` is, and what is still exposed on the other hypervisors.

## Findings that are not in the change

- **No automation of ours pins or restarts tailscale.** The `apt-get install --allow-downgrades tailscale=X` is `tailscale update`'s own, triggered by the control plane (`AutoUpdate.Apply: true` on all four hypervisors).
  Turning that off (`tailscale set --auto-update=false` per node, or the tailnet-wide default) is a decision for the user.
- **#659 (0docker) is half a fix.** `woodpecker-exec-proxy@.socket` has no `FreeBind`: the device `Wants=` starts it 0.8 s before the address exists and the bind fails (rig rows `role-wants`). It needs a `FreeBind` drop-in;
  `zdocker-hypervisor-metrics-proxy.socket` needs a device `Wants=` (the rig's `role-freebind` stop/start row). Separate change, 0docker: `ws-20261103-tailscaled-restart-0docker`.
- **`pg-replica-tailnet.service`** was a leftover of the retired `pg-primary` replica path (one iptables MASQUERADE rule); it failed on the xtables lock during the 2026-10-11 dist-upgrade and did not matter. **Retired on 2026-11-03 09:07:42Z** with the user's yes (backup in
  `/root/retired-pg-replica-tailnet-20261103T090742Z`, root only; undo = copy the unit and the script back and `daemon-reload`).

## Verification

`python3 scripts/hostconf.py check` (42 hosts, 87 files), the new tests and the hostconf and fleet-observability tests, `systemd-analyze verify` inside the rig, the rig itself (`scripts/tailscaled_restart_rig/run.sh`,
systemd 257 and 252), then the repository pre-push gate on the build server. After the apply: `python3 scripts/hostconf.py drift --host pve-0mcp`; the live proof was the controlled tailscaled restart of 2026-11-03 09:16:25Z (all 21 sockets active throughout).

## Rollback

Remove the drop-ins on the hypervisor and `systemctl daemon-reload`, or revert the commit and apply again. The template and inventory changes matter only at the next converge of the roles.
