# Runbook: the tailnet proxy sockets across a tailscaled restart (0mcp hypervisor)

Workstreams `ws-20261102-tailscaled-restart-proxies` (0mcp) and `ws-20261103-tailscaled-restart-0docker` (0docker). The sections up to "Decision for the user" describe the 0mcp hypervisor (`pve-0mcp`, ssh `operator-bastion`, tailnet `100.64.0.6`);
"0docker hypervisor" is the same fix for the 0docker hypervisor (hostconf id `bastion`, host `pve-0docker`, ssh `0docker_bastion`, tailnet `100.64.0.5`, systemd 252); the last section lists what is left on the other hypervisors.

## What happened on 2026-11-02

At 12:33 CET `tailscaled` on both the 0mcp and the 0docker hypervisor updated itself. It was **not** automation of ours: the Tailscale control plane sent a client-update request (`c2n: POST /update`),
tailscaled ran `systemd-run --wait --pipe --collect /usr/bin/tailscale update --yes`, and that ran `apt-get install --yes --allow-downgrades tailscale=1.104.4` (history.log: 12:33:26, 1.104.1 to 1.104.4;
0docker 12:33:24). The pin is `tailscale update`'s own: no role or script in this repo installs or pins a tailscale version (`proxmox_tailscale` uses `state: present`). Both hypervisors carry
`AutoUpdate: {Check: true, Apply: true}` in `tailscale debug prefs`, and so do `0own_bastion` and `0infer_bastion`.

The same update is what stopped the Woodpecker exec proxy on 0docker (workstream `ws-20261102-exec-proxy-tailscale0`, "what made tailscale0 flap was not found"): 12:33:24 CET is 11:33:24Z.

Timeline of the 0mcp journal (CET):

| Time | Event |
|---|---|
| 12:33:22 | `c2n: POST /update received`, `tailscale update --yes` started |
| 12:33:28.88 | the package's postinst restarted tailscaled; systemd stopped **every unit with `Requires=tailscaled.service`**: the 19 `lv3-tailscale-proxy-*` sockets and services, `zmcp-runtime-general-metrics-proxy`, `woodpecker-0exec-build-metrics-proxy` and two route services, then tailscaled |
| 12:33:31.90 | `Started tailscaled.service` (it is `Type=notify` and reports ready **before** it creates its device) |
| 12:33:31.90 | the 19 lv3 sockets: `Bound to unit sys-subsystem-net-devices-tailscale0.device, but unit isn't active` then `Dependency failed`: they have `BindToDevice=tailscale0`, which makes systemd add `BindsTo=` and `After=` on the device unit |
| 12:33:31.908 | tailscaled: `Creating WireGuard device` (tailscale0 exists from here) |
| 12:33:31.919 | `woodpecker-0exec-build-metrics-proxy.socket`: **Listening** (it has `FreeBind=true`, added after the 2026-10-11 incident) |
| 12:33:31.922 | `zmcp-runtime-general-metrics-proxy.socket`: `Failed to create listening socket (100.64.0.6:9101): Cannot assign requested address` |
| 12:33:32.71 | the tailnet address is on tailscale0 (`peerapi: serving on http://100.64.0.6`), 0.8 s after "started" |
| about 20:58 | restored by hand (`reset-failed` + `start`): 8 hours without OpenBao, Postgres, Vaultwarden, Gitea, Woodpecker, Plane, Portainer, Windmill, Mattermost and 10 more proxies; the alert that showed it was `FleetNodeExporterDown` for runtime-general |

It has happened before: 2026-10-11 00:52 (`apt-get dist-upgrade`, tailscale 1.102.2 to 1.104.1) killed the build-metrics proxy the same way (`docs/runbooks/fleet-observability.md`, "Why `FreeBind=true`"), and the
tailscale package was replaced the same way at 2026-08-07 12:51 (`apt-get install --yes --allow-downgrades tailscale=1.102.2`, the signature of `tailscale update`). Every tailscale update, and every tailscaled crash that restarts it, hits the sockets again.

## The fix

Two settings, both needed (the rig below shows each alone is not enough):

| Part | What it does | Where in git | How it reaches the host |
|---|---|---|---|
| `FreeBind=true` in `[Socket]` | the bind succeeds before tailscale0 has its address (`IP_FREEBIND`); the connection works as soon as the address is back | role template `lv3-tailscale-proxy.socket.j2` (new renders), `free_bind: true` for `zmcp-runtime-general-metrics-proxy` in `inventory/fleet-observability.yml`, hostconf `socket-free-bind.*` (20 drop-ins `20-free-bind.conf`) | hostconf drop-ins now (`daemon-reload` only); the role the next time it is converged |
| `Wants=` on the device unit `sys-subsystem-net-devices-tailscale0.device` | systemd starts every proxy socket when the device becomes active, which fixes the sockets that failed because the device was not active when they were started (the 19 lv3 sockets) and the two node-exporter sockets that nothing starts after `stop` + `start` of tailscaled | hostconf `tailscale0-wants-lv3-proxies` (`/etc/systemd/system/sys-subsystem-net-devices-tailscale0.device.d/10-wants-lv3-tailscale-proxies.conf`, 21 names) | hostconf drop-in (`daemon-reload` only) |

Nothing restarts: `FreeBind` takes effect when a socket next starts, the device `Wants=` when the device next appears.

Why this and not the alternatives:

- **`FreeBind` alone** does not fix the 19 lv3 sockets: their start job fails on the `BindsTo=` of the device before it ever binds (rig rows `role-freebind`).
- **The device `Wants=` alone** starts them 0.8 s too early: the bind then fails with `Cannot assign requested address` (rig rows `role-wants`).
- **Dropping `BindToDevice=tailscale0`** would remove the `BindsTo=` and make `FreeBind` enough, but it also removes the guarantee that the socket only answers on tailscale0. It is a security decision, not a fix; kept.
- **`Upholds=` instead of `Wants=`** would also restart a socket an operator stopped on purpose while tailscale0 is up. `Wants=` is a one-time pull when the device appears (rig row `operator stop stays`).
- **A `tailscaled.service` drop-in with `ExecStartPost=`** runs before the device exists (tailscaled reports ready first) and would delay every unit ordered after tailscaled at boot.
- **Removing `Requires=tailscaled.service`** changes what stops with tailscaled; not needed once the sockets come back by themselves.

## Proof: `scripts/tailscaled_restart_rig`

A privileged systemd container (`--network none`, on `0mcp_docker_build`, never on a hypervisor) boots the real templates and the real hostconf files with a stand-in tailscaled that has the timing of the journal above
(ready, device 50 ms later, address 0.8 s after that) and restarts it four ways. Result, systemd 257 (the hypervisor's version, `debian:trixie`); `ok after N ms` is time until all five modelled sockets listen:

| Variant | boot | `systemctl restart` (apt) | `kill -9` | `stop`, 2 s, `start` |
|---|---|---|---|---|
| `role-none` (before the fix) | 4 of 5 dead | 4 of 5 dead | 4 of 5 dead | 5 of 5 dead |
| `role-freebind` (FreeBind only) | ok | **3 lv3 sockets dead** | ok | 2 node-exporter sockets dead |
| `role-wants` (device `Wants=` only) | 4 of 5 dead | 4 of 5 dead | 4 of 5 dead | 4 of 5 dead (`Cannot assign requested address`) |
| `role-fix` (both) | ok 31 ms | ok 278 ms | ok | ok 281 ms |
| `hostconf-fix` (the live layout: old main units plus the hostconf drop-ins) | ok 32 ms | ok 275 ms | ok | ok 262 ms |

`systemd-analyze verify` is clean for every variant, and in `hostconf-fix` the two properties hostconf proves the files by read as expected (`systemctl show -p FreeBind` is `yes` for every socket, `-p Wants` of the device unit lists 21 sockets; `no` and 0 in `role-none`). An operator's `systemctl stop <proxy>.socket` stays stopped in the fix variants. The same run on `debian:bookworm` (systemd 252, the 0docker hypervisor) gives the same picture: `role-none` and `role-wants` dead in every event, `role-freebind` dead after `restart` and after `stop` + `start`, `role-fix` and `hostconf-fix`
all ok (25 to 277 ms). The rig exited 0 (`RIG OK`) on both.

In the fix variants the journal still shows `Bound to unit sys-subsystem-net-devices-tailscale0.device, but unit isn't active` once per lv3 socket during a restart: that is the first, failed start; the device
`Wants=` starts them again about 0.3 s later. It is expected, not an error. The `lv3-tailscale-proxy-*.service` units restarted by the same propagation fail with `Didn't get any sockets passed in` and show as
`failed` until `systemctl reset-failed 'lv3-tailscale-proxy-*.service'` (the role clears them at its next converge); they are socket-activated and start again on the next connection.

Run it again after any change to the units (on a build host with docker, never on a hypervisor; details in `scripts/tailscaled_restart_rig/README.md`):
`build_variants.py --out TREES`, then `scripts/tailscaled_restart_rig/run.sh TREES trixie bookworm` (exit 0 only when every fix variant keeps all its sockets and the baselines `role-none` and `docker0-live` show the failure; the `docker0-*` variants of the 0docker hypervisor run on `bookworm`). `tests/test_tailscaled_restart_proxies.py` keeps the proxy catalog, the inventory of the node-exporter proxies and the hostconf
catalog (`socket-free-bind.*`, `tailscale0-wants-lv3-proxies`) equal, so a new proxy that is not in all of them fails the test.

## Apply (needs the user's yes; applied on pve-0mcp on 2026-11-03)

**Done 2026-11-03 09:06:53Z** (PR 661, the user's yes) through `hostconf.py apply --host pve-0mcp` with the 21 files (20 `socket-free-bind.*` and `tailscale0-wants-lv3-proxies`): exit 0, hostconf's own read-back all ok, no unit restarted. Read-only checks afterwards: the device `Wants` lists 21 sockets, `FreeBind=yes` on all 21, all 21 sockets active, 25 listeners on `100.64.0.6`, Prometheus `up{9101}` 1 and :9101 answering 200. The commands below are what was run.

Compare first, then apply only these files. hostconf backs the old file up, writes atomically, runs `daemon-reload` and checks the property, it never restarts a unit:

```sh
python3 scripts/hostconf.py drift --host pve-0mcp                                   # the 21 new entries show as missing
files=$(grep -o -E '^  (socket-free-bind\.[a-z0-9.-]+|tailscale0-wants-lv3-proxies):' config/hostconf/hostconf.yaml | tr -d ' :' | sed 's/^/--file /' | tr '\n' ' ')
python3 scripts/hostconf.py apply --host pve-0mcp $files            # without --yes: prints the plan, changes nothing
python3 scripts/hostconf.py apply --host pve-0mcp $files --yes
python3 scripts/hostconf.py drift --host pve-0mcp                                   # no drift
```

Read-only checks afterwards:

```sh
ssh operator-bastion 'systemctl show -p Wants sys-subsystem-net-devices-tailscale0.device | tr " " "\n" | grep -c "socket$"'        # 21
ssh operator-bastion 'systemctl show -p FreeBind lv3-tailscale-proxy-openbao.socket zmcp-runtime-general-metrics-proxy.socket'      # FreeBind=yes (also after the next start)
ssh operator-bastion 'systemctl is-active lv3-tailscale-proxy-*.socket zmcp-runtime-general-metrics-proxy.socket woodpecker-0exec-build-metrics-proxy.socket | sort | uniq -c'
```

The running sockets kept their old setting until they next started, so the proof on the hypervisor is a tailscaled restart. **Live test, 2026-11-03 09:16:25Z** (the user's yes: "do it so we can check"): `systemctl restart tailscaled` on pve-0mcp with the 21 files applied, measured by a detached logger on the host
(`/root/tsrestart-test-20261103T091625Z.log`, script `/root/tsrestart_test.sh`; recorded here from the session that ran it): the command returned after 2.56 s, the `tailscale0` device existed at 2.57 s, the tailnet address at 3.46 s, the listeners on the tailnet IP were back to 25 (baseline 25) at 4 s,
and **all 21 proxy sockets reported active in every sample (21 of 21 throughout, none dead)**. As the rig predicted, the 19 `lv3-tailscale-proxy-*.service` units showed `failed` afterwards (`Didn't get any sockets passed in`); `systemctl reset-failed 'lv3-tailscale-proxy-*.service'` cleared them (no failed unit left) and they started
again on the next connection, so that step stays advisable after a restart. End to end afterwards: the Woodpecker proxy :8017 answered 204, Gitea :3009 200, the node-exporter proxy :9101 200 and Prometheus `up` was 1 for 9101, 9102 and 9103; OpenBao :8200 completes the TLS handshake through its proxy (it requires a client certificate,
the same answer as asked directly on 10.10.10.92:8200). The route units (`woodpecker-0exec-route-docker-build`, `woodpecker-exec-private-route`), node-exporter and aivoicebus stayed or came back active. A real Tailscale auto-update takes the same path (a stop and start of tailscaled), so this is the proof for 0mcp; it cost
about 3 s of tailnet and no proxy socket. The 0docker hypervisor has not been tested live (see its section below).

Rollback: remove the files (`/etc/systemd/system/<unit>.socket.d/20-free-bind.conf`, the device drop-in) and `systemctl daemon-reload`, or revert the commit and apply again. The role template and the inventory change
only matter at the next converge of `proxmox_tailscale_proxy` / `fleet_node_exporter` on this host, which restarts a socket whose unit text changed: converge in a window, or apply the hostconf files first so the role finds nothing to restart.

## Decision for the user: tailscale's self-update

All four hypervisors (0mcp, 0docker, 0own, 0infer) have `AutoUpdate.Apply: true`, so the control plane can restart tailscaled on any of them at any time; the same update hit two of them in the same minute.
With this fix a restart costs the 0mcp proxies under a second, but it is still an unplanned 3 s cut of the tailnet on the subnet routers, at a time nobody chose, with `--allow-downgrades` and a version nobody pinned.
Options (not done by this change):

- keep auto-update (security patches arrive by themselves) and accept the blip; or
- turn it off per hypervisor: `tailscale set --auto-update=false` (a preference in tailscaled's state, not a file: hostconf cannot hold it; `fleet_tailscale_node` manages only advertised routes), and update by `apt-get install tailscale`
  in a window; or
- turn it off for the whole tailnet in the Tailscale admin console (the tailnet-wide client auto-update default), which also covers the VMs and containers.

## `pg-replica-tailnet.service` (failed since 2026-10-11 00:53, retired 2026-11-03)

A `Type=oneshot` unit (`RemainAfterExit`, `Requires=tailscaled.service`) whose script `/usr/local/sbin/pg-replica-tailnet` (written 2026-09-24) installs one iptables rule:
`-t nat POSTROUTING -s 10.10.10.53/32 -d 100.64.0.10/32 -o tailscale0 -p tcp --dport 5432 -j MASQUERADE`, so that a Postgres replica at 10.10.10.53 could reach the old `pg-primary` (tailnet 100.64.0.10) over the tailnet.
It failed with exit status 4 (iptables' "resource problem": the xtables lock was held) at 00:53:07 on 2026-10-11, 47 s into the `apt-get dist-upgrade` that also updated tailscale (the same night the build-metrics proxy died),
and nothing ran it again. **It does not matter any more**: the rule is absent, no guest config in `/etc/pve` names 10.10.10.53, and `pg-primary` has been offline for 12 days (`tests/test_infer_pg_primary_direct.py`
records that 100.64.0.10 left the tailnet when production Postgres moved to VM701). It only kept `systemctl --failed` non-empty.

**Retired on 2026-11-03 09:07:42Z with the user's yes** (separate from this change, on the host only): before removal its iptables rule was absent and no file or guest config referenced the unit or 10.10.10.53; the unit and the script were backed up to `/root/retired-pg-replica-tailnet-20261103T090742Z` (root only), then `systemctl disable`, `reset-failed`, the unit file and `/usr/local/sbin/pg-replica-tailnet` removed and `daemon-reload`; `systemctl --failed` is empty. Undo: copy the two files back from that directory and `systemctl daemon-reload`.

## 0docker hypervisor

Workstream `ws-20261103-tailscaled-restart-0docker`. Git only until the apply below; read-only ssh was all that touched the host.

### What happened there on 2026-11-02 (journal of the hypervisor, CET)

| Time | Event |
|---|---|
| 12:33:22 | `c2n: POST /update`, `tailscale update --yes` (the same self-update as on 0mcp, see above) |
| 12:33:27 | systemd stopped every unit with `Requires=tailscaled.service` (the woodpecker and zdocker sockets and services, the two socat relays), then `Stopping tailscaled.service` |
| 12:34:57 | **`tailscaled.service: State 'stop-sigterm' timed out. Killing.`**: the stop took the whole 90 s (`TimeoutStopSec`); why it hung was not looked into (tailscaled had a number of tailscale SSH sessions open and the host runs hot) |
| 12:34:59.942 | `Started tailscaled.service` |
| 12:34:59.943 | `woodpecker-exec-proxy@9000.socket: Bound to unit sys-subsystem-net-devices-tailscale0.device, but unit isn't active` (BindToDevice=tailscale0 makes the socket `BindsTo=` the device): dead; the CI plane (`ci.0exec.com`) stood still for 71 minutes (`ws-20261102-exec-proxy-tailscale0`) |
| 12:34:59.946 | tailscaled: `Creating WireGuard device` (device 4 ms after "started") |
| 12:34:59.957 | `zdocker-hypervisor-metrics-proxy.socket`: Listening (FreeBind, no device needed) |
| 12:34:59.958 / .960 | `0memory-postgres-relay.service` and `registrant-postgres-relay.service` started again (restart propagation) |
| 12:35:00.252 | `peerapi: serving on http://100.64.0.5`: the address is on tailscale0 **0.31 s after "started"** (0.8 s on 0mcp, which the rig keeps as the harder case) |

PR 659 (`woodpecker-exec-proxy-follows-tailscale0`, applied 2026-11-02 15:41) made the device `Want` the woodpecker socket. That fixes the 12:34:59.943 failure, and it hands the problem to the next one: the start the device triggers comes
before the address exists, and a socket without FreeBind then fails with `Cannot assign requested address` (the rig, row `docker0-live` below; on 0mcp the rows `role-wants`).

### Scan of the hypervisor (read-only, 2026-11-03 10:08 CET, systemd 252, tailscale 1.104.4)

Every unit that names `tailscaled.service` in `Requires=`/`BindsTo=`/`PartOf=`, every socket that listens on the tailnet address or has `BindToDevice=tailscale0`, and every other listener on `100.64.0.5` (`ss`):

| Unit | What it binds | What a tailscaled restart does to it | In this change |
|---|---|---|---|
| `woodpecker-exec-proxy@9000.socket` | `100.64.0.5:9000`, `BindToDevice=tailscale0`, **no FreeBind** (the only instance of the template that is enabled) | dead: "device isn't active", and after PR 659's `Wants=` "Cannot assign requested address" | **FreeBind drop-in on the template** |
| `zdocker-hypervisor-metrics-proxy.socket` | `100.64.0.5:9100`, FreeBind, only `WantedBy=sockets.target` | comes back with a restart (12:34:59.957); **stays dead after a separate `stop` and `start`** of tailscaled | **device `Wants=`** |
| `woodpecker-exec-proxy@9100.socket` | stale instance, disabled on purpose (`fleet_node_exporter_socket_proxies`, `state: disabled`: it would collide on :9100) | not loaded | kept out of every `Wants=` (a test pins it) |
| `0memory-postgres-relay.service`, `registrant-postgres-relay.service` (`Requires=tailscaled.service`, `Restart=always`) | socat on `10.10.10.1:5432` and `:15432` (the vmbr1 bridge address, not the tailnet address) towards `100.64.0.22:5432` | stopped with tailscaled and started again by the restart (12:34:59.958/.960); like the node-exporter socket they would stay stopped after a separate `stop` and `start` | no: see "Not covered" |
| `woodpecker-private-route.service`, `dockerhost-pbs-relay.service` (oneshots, `Wants=`/`After=tailscaled.service`) | iptables and nft rules that match `-o tailscale0` / `oifname "tailscale0"` by name | not stopped; rules that match an interface by name survive the device going away | no |
| `fleet-msg.service`, `tailscale-wait-online.service` | `fleet-msg` is inactive and not enabled; `tailscale-wait-online` is a distro oneshot | nothing at risk | no |
| `aivoicebus.service` (`100.64.0.5:7777`), the docker-proxy of `scanopy-gzip` (`100.64.0.5:60080`), tailscaled's own listeners | plain processes, no dependency on `tailscaled.service` | not stopped by the restart (their boot-order against the address is a separate question) | no |

So on this host two sockets bind the tailnet address, and they are exactly the two in the task above; the other `Requires=tailscaled.service` units bind nothing on it.

Not covered, on purpose: **the two relays** come back after a restart and after a crash and are down only after a separate `stop` and `start`; to cover that they would have to be `Wants=` of the device as well, which would start a relay
that someone stopped or (for `registrant-postgres-relay`, whose unit text still says "INSTALLED DISABLED AND NOT STARTED" although it is enabled and has run for hours) disabled on purpose, at the next tailscaled restart. That is a decision for
whoever owns the relays, not a side effect of this change.

### The change (two hostconf files, nothing in a role: the woodpecker template is hand-installed and not in git)

| Part | hostconf entry | File on the host |
|---|---|---|
| `FreeBind=true` on the template | `socket-free-bind.woodpecker-exec-proxy` | `/etc/systemd/system/woodpecker-exec-proxy@.socket.d/20-free-bind.conf` |
| the device `Wants=` the node-exporter proxy | `tailscale0-wants-zdocker-metrics-proxy` | `/etc/systemd/system/sys-subsystem-net-devices-tailscale0.device.d/10-wants-zdocker-hypervisor-metrics-proxy.conf` |

The second is a new drop-in next to PR 659's `10-wants-woodpecker-exec-proxy.conf` (systemd adds up `Wants=`), so the applied file is not rewritten. Because two drop-ins now add to one list, PR 659's entry proves its name with `contains:` instead of
`value:` (an exact match of the whole list would report drift on it after the second file is applied); `tests/test_tailscaled_restart_0docker.py` pins that. Nothing restarts: FreeBind takes effect when a socket next starts, the device `Wants=` when the device next appears.

### Proof: the `docker0-*` variants of the rig (systemd 252, `debian:bookworm`)

The units are the ones read from the host (`scripts/tailscaled_restart_rig/0docker-units/` for the hand-installed template; the role template for the node-exporter proxy), the drop-ins are the real hostconf files, the stand-in tailscaled has the 0docker address.
The variants are an ablation on top of what is live now (PR 659 applied): `docker0-live` (nothing more), `docker0-freebind` (the FreeBind drop-in only), `docker0-wants` (the device `Wants=` of the node-exporter proxy only), `docker0-fix` (both: this change).

Result on `debian:bookworm` (systemd 252, the hypervisor's version); `ok after N ms` is the time until both modelled sockets listen, `dead` names the sockets that stayed down for the 12 s the rig waits:

| Variant | boot | `systemctl restart` (apt) | `kill -9` | `stop`, 2 s, `start` |
|---|---|---|---|---|
| `docker0-live` (PR 659 applied, nothing more) | woodpecker dead | woodpecker dead | woodpecker dead | woodpecker and zdocker dead |
| `docker0-freebind` (FreeBind drop-in only) | ok 12 ms | ok 222 ms | ok 223 ms | **zdocker dead** |
| `docker0-wants` (device `Wants=` of zdocker only) | woodpecker dead | woodpecker dead | woodpecker dead | woodpecker dead |
| `docker0-fix` (both: this change) | ok 11 ms | ok 222 ms | ok 222 ms | ok 230 ms |

The woodpecker socket dies in `docker0-live` and `docker0-wants` with `Failed to create listening socket (ADDR): Cannot assign requested address`: PR 659's `Wants=` starts it as soon as the device exists, 0.8 s before the address, which is the half-fix the 0mcp rig
predicted (`role-wants`). FreeBind alone keeps the woodpecker socket (the `Wants=` of PR 659 starts it again about 0.2 s after the first, failed start) but not the node-exporter proxy after `stop` + `start`; the device `Wants=` alone keeps the proxy but not the
woodpecker socket. Both together keep both in every event. `systemd-analyze verify` is clean for every variant; in `docker0-fix` the properties hostconf proves the files by read `FreeBind=yes` for both sockets and the device `Wants=` lists both (`no`/`yes` and one socket in
`docker0-live`); an operator's `systemctl stop woodpecker-exec-proxy@9000.socket` stays stopped. The journal of `docker0-fix` shows `Bound to unit sys-subsystem-net-devices-tailscale0.device, but unit isn't active` once: the first, failed start, expected as on 0mcp.
The rig's boot row has the stand-in tailscaled starting with the system; it is a model, not the host's boot (the host last booted on 2026-10-13, before PR 659 and this change). The rig exited 0 (`RIG OK`).

### Apply (needs the user's yes; nothing is applied by the pull request)

hostconf resolves `bastion` as an ssh alias (`ssh: bastion` in `config/hostconf/hostconf.yaml`): check `ssh -G bastion` on the machine that runs it (it must be the 0docker hypervisor, tailnet `100.64.0.5`; the alias `0docker_bastion` is the same host), and `apply` refuses another machine by its `hostname`.

```sh
python3 scripts/hostconf.py drift --host bastion                                     # the two new entries show as missing, nothing else
python3 scripts/hostconf.py apply --host bastion --file socket-free-bind.woodpecker-exec-proxy --file tailscale0-wants-zdocker-metrics-proxy          # without --yes: prints the plan, changes nothing
python3 scripts/hostconf.py apply --host bastion --file socket-free-bind.woodpecker-exec-proxy --file tailscale0-wants-zdocker-metrics-proxy --yes
python3 scripts/hostconf.py drift --host bastion                                     # no drift (PR 659's entry still holds: it uses contains)
```

Before the apply, `drift --host bastion` (read-only, run on 2026-11-03 against the live host) shows exactly four lines and every other entry `ok`: `MISSING` for the two new files and `NOT IN EFFECT` for `woodpecker-exec-proxy@9000.socket.FreeBind` (live `no`) and for the device `Wants` (live: only the woodpecker socket).

Read-only checks afterwards:

```sh
ssh 0docker_bastion 'systemctl show -p FreeBind woodpecker-exec-proxy@9000.socket zdocker-hypervisor-metrics-proxy.socket'     # FreeBind=yes twice
ssh 0docker_bastion 'systemctl show -p Wants sys-subsystem-net-devices-tailscale0.device | tr " " "\n" | grep "socket$"'        # both sockets
ssh 0docker_bastion 'systemctl is-active woodpecker-exec-proxy@9000.socket zdocker-hypervisor-metrics-proxy.socket'              # active, active (the running sockets are not touched)
ssh 0docker_bastion 'ss -ltn | grep -E "100.64.0.5:(9000|9100) "'                                                          # both still listening
```

The running sockets keep their old setting until they next start, so the first proof on the hypervisor is the next tailscaled restart (an update, a crash). A controlled one is a choice for the user and is not free here: on 2026-11-02 the stop alone took 90 s,
the tailnet (and with it every Woodpecker agent) was away for that long, and the host has been observed at load 30 and more; the rig is the evidence until then. Watch the first one with `journalctl -u 'woodpecker-exec-proxy@*' -u zdocker-hypervisor-metrics-proxy.socket -f`:
`Bound to unit ... isn't active` once, then `Listening on` about 0.3 s later is the expected picture, as on 0mcp.

Rollback: `ssh 0docker_bastion 'rm /etc/systemd/system/woodpecker-exec-proxy@.socket.d/20-free-bind.conf /etc/systemd/system/sys-subsystem-net-devices-tailscale0.device.d/10-wants-zdocker-hypervisor-metrics-proxy.conf && systemctl daemon-reload'`
(PR 659's drop-in and the ordering drop-ins stay), or revert the commit and apply again.

## What is still exposed (read-only scans, 2026-11-02 and 2026-11-03)

- 0docker hypervisor: covered by the section above once its two hostconf files are applied (until then both gaps are open: `woodpecker-exec-proxy@9000.socket` has no `FreeBind`, `zdocker-hypervisor-metrics-proxy.socket` is not `Wants=`ed by the device).
  Left there: the two socat relays after a separate `stop` and `start` of tailscaled.
- 0own and 0infer hypervisors: no socket binds the tailnet address (`ListenStream=100.` or `BindToDevice=tailscale0`); the node-exporter drop-ins (`node-exporter-after-tailscale`, `-wait-for-tailscale`, `-retry-until-tailnet`) cover the exporter.
- VMs and containers with their own tailscaled were not scanned.
