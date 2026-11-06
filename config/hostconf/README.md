# hostconf: host-local configuration under version control

Some configuration lives on one host and nowhere else: the systemd drop-in that makes nginx restart after an OOM kill, the sysctl file that lifts the
thread limit of a VM with hot-plugged memory, a Postgres setting. Nobody can review it, a rebuilt VM loses it, and a hand edit changes it without a trace.
`hostconf.yaml` lists, per host, the files that must exist and the effective setting each one has to produce; `scripts/hostconf.py` compares the live
hosts with it and, on request, writes the files. Written 2026-10-19 after the changes of that day (nginx and Postgres restart policy, `log_connections`,
the thread limit) turned out to be on the hosts only.

## What is managed

| Kind | Destination (fixed in the code, not in the manifest) | After a change | Proven in effect by |
|---|---|---|---|
| systemd drop-in | `/etc/systemd/system/<unit>.d/*.conf` (a service, socket, timer, path, mount, ... or **device** unit: a `.device` drop-in with `Wants=` starts a socket bound to that device when it comes back) | `systemctl daemon-reload` | `systemctl show <unit> --property <p> --value` |
| sysctl | `/etc/sysctl.d/NN-*.conf` | `sysctl -p <file>` | `sysctl -n <key>` |
| Postgres conf.d | `/etc/postgresql/<version>/<cluster>/conf.d/NN-*.conf` | `pg_ctlcluster <version> <cluster> reload` | `SHOW <name>` |

The tool never restarts or stops anything, never writes anywhere else, and refuses a file that looks like it holds a credential (a password, token, key, or a URL with
a password; `LoadCredential=` / `ImportCredential=` name a file and are fine), in the repo and on the host. A setting that needs a restart (Postgres `shared_buffers`, `listen_addresses`) is reported as pending and left to a human.

Today: 89 catalog files on 45 hosts, which is every machine of the fleet: the five hypervisors and all 40 VMs and containers they run, two VMs (the SPIRE servers) reached only through their hypervisors' guest agent (`python3 scripts/hostconf.py check` prints the count). By family:

- restart and OOM policy: nginx on the 0docker gateway, the 0mcp gateway and the 0docker hypervisor (`Restart=on-failure`, `OOMPolicy=continue`); `OOMPolicy=continue` for the three Postgres clusters
  that had `Restart=no` and the default `OOMPolicy=stop`; the tailnet ordering and `log_connections` of the production DomainScope Postgres;
- boot ordering around Tailscale (the 2026-10-13 incidents): 23 tailnet proxy sockets of the 0mcp and 0docker hypervisors without default dependencies (an ordering cycle made systemd delete start
  jobs, tailscaled included), and the node-exporter drop-ins that wait for tailscaled, retry without a start limit or restart always (14 hosts; own-pbs, 0own-openobserve, github-mirror and pdm added 2026-10-31 after a reboot of all four lost the race with tailscaled); and, since 2026-11-02, what keeps the 0mcp hypervisor's 21 tailnet proxy sockets alive across a tailscaled restart (a self-update killed 20 of them for 8 hours): `FreeBind=true` drop-ins (`socket-free-bind.*`) and a `Wants=` drop-in of the `tailscale0` device unit (`tailscale0-wants-lv3-proxies`); on the 0docker hypervisor the same two parts for `woodpecker-exec-proxy@.socket` (`socket-free-bind.woodpecker-exec-proxy` with PR 659's device `Wants=`) and for `zdocker-hypervisor-metrics-proxy.socket` (`tailscale0-wants-zdocker-metrics-proxy`), see `docs/runbooks/tailscaled-restart-proxies.md`;
- CVE-2026-98432 stop-gap (2026-10-31): `net.mptcp.enabled = 0` on every host (`sysctl-disable-mptcp`), because the demonstrated exploit needs an MPTCP listener. It is per network namespace: it covers the host's own
  listeners (tailscaled, nomad, alloy, host-network containers) and NOT containers with their own namespace, and an open listener stays MPTCP until its service restarts. Remove it once a fixed kernel runs everywhere;
- kernel limits: `kernel.threads-max = 131072` on 22 hot-plug VMs (below), dockerhost's own `threads-max 2000000` and ARP table sizing (`90-fleet-neigh-gc.conf`), `vm.swappiness` on the 0mcp guests and `vm.swappiness = 10` on the production Postgres VM next to its 16 GiB root-disk swapfile (2026-10-31; the swapfile and its fstab line are not managed files, the entry's purpose gives the rebuild commands), IP
  forwarding on the hypervisors, IPv6 off on the gateway, `rp_filter` on the Hermes VM;
- dockerhost, the hypervisors and single hosts: docker `LimitNOFILE`, fstrim and logrotate timers, the vzdump-aware CT108 trim, Scanopy `FreeBind`, the nftables hooks, the incident-control metrics,
  the 0own build worker's NFS/rpcbind, Caddy and the Hermes release path, the aivoicebus observer credential reference.

### The fleet baseline: no machine under 131072 threads

`baseline:` in `hostconf.yaml` is a floor that **every** host of the manifest must meet, whether or not it carries a file: today `kernel.threads-max >= 131072`. `drift --all` reads the live value on each
machine (`BELOW BASELINE sysctl kernel.threads-max: live '63375', wanted >= 131072; add sysctl-hotplug-threads-max ...`) and exits 2 when one is below. It is a floor, not a fixed value: the hypervisors
(boot defaults of 470000-960000), dockerhost and docker-prod (2000000), CT108 and the big VMs are already above it and carry no file, because a file with `131072` would *lower* them. The 25 hot-plug VMs
and the six small 0own VMs (31 in all) that boot below it carry `sysctl-hotplug-threads-max`. The three LXC containers of the 0docker hypervisor share its kernel and are listed only so that the check covers them.

Four layers keep the class of failure from coming back: (1) the baseline above, run by whoever runs `drift --all`; (2) the **inventory**: `inventory:` names the hypervisors and every host of the
manifest says which guest it is (`vm: {hypervisor: pve-0mcp, id: 120}`); `drift --all` (or `drift --inventory`) runs `qm list` and `pct list` on each hypervisor and prints
`UNMANAGED  VM 151 postgres-replica-lv3 (running): ...` for a guest that is neither a host nor exempt (`inventory.exempt`, each with a reason), `GONE` for a host whose guest no longer exists and
`STALE EXEMPTION` for an exemption that no longer applies. This is what a hand-made scan on 2026-10-19 lacked: it missed three 0mcp VMs, which still had the 7000-thread limit; (3) new guests rendered from the
Ansible role (`proxmox_guests/templates/user-data.yml.j2`) get the same file from their first boot through cloud-init, like they keep their SSH host keys (a test pins that the template, the catalog file and the
baseline agree on the value); (4) the root cause, memory hot-plug on the VM, is documented below and can be switched off per VM at a maintenance window. A VM created by hand with `qm clone` from a template does
not go through the role: the inventory reports it on the next `drift --all`, and the baseline then tells whether it needs the file.

A guest no operator can ssh into (the two SPIRE servers, VM 103 and VM 705, have no operator key) is a host with `vm` and **no `ssh`**: the same script is piped through `qm guest exec <id> --pass-stdin` on its hypervisor,
so drift, apply and the baseline work on it too. It needs the QEMU guest agent and `python3` in the guest.

### The scheduled check: layers 1 and 2 without anybody having to remember

`scripts/hostconf-scheduled.sh` runs `drift --all` once a day from the operator's machine (a macOS LaunchAgent, 12:20 local: the builder has no ssh keys to most of these hosts, the operator's machine has them
all) and ships the result to the monitoring VM as the node_exporter textfile `/var/lib/prometheus/node-exporter/fleet_hostconf.prom`. The alerts are in `config/prometheus/rules/fleet-hostconf.yml`:
`HostconfBelowBaseline` (the thread floor), `HostconfDrift`, `HostconfInventoryFinding` (a guest nobody added to the manifest), `HostconfMachineUnreachable` and `HostconfInventoryUnreachable` (two daily runs
in a row), and `HostconfCheckStale` / `HostconfCheckMissing`: the job itself has not delivered for 36 hours, so a machine that sleeps or an ssh key that expired cannot end the checking silently. The job is read-only
(`drift` only; a test pins that it never runs `apply` or `adopt`), takes the tool and the manifest from main on every run (a depth-1 sparse checkout of two paths) and keeps no credential: it uses the operator's
ssh configuration. `scripts/hostconf-scheduled.sh install | status | uninstall`; the log is `~/Library/Logs/hostconf-drift.log`. What each alert means and what to do: `docs/runbooks/host-local-config.md`.

### Why `kernel.threads-max`

A VM whose memory is hot-plugged (Proxmox `hotplug: ...memory`) gets its thread limit from the memory the kernel sees at boot, about 1 GB: `kernel.threads-max` is about 7000
whatever the VM's real size (a 16 GB VM would get 130000; the VMs below showed 6745-7020). `qm config` on the 0mcp, 0infer, 0docker and 0database hypervisors shows
`hotplug: ...,memory` and `numa: 1` on every one of them, and none on pg-primary (96 GB, `hotplug: disk,network,usb,cpu`), whose limit is right. On 2026-10-19 at 17:29:23Z infer-runtime (273 containers, 30 vCPU, about 9000 threads at
steady state) rebooted and Docker started every container at once: for two seconds `fork()` and `pthread_create()` returned EAGAIN (dockerd, containerd-shim, sshd, udev and a kernel worker all
logged it; no cgroup limit was hit), dozens of container starts failed, and 22 containers ended up *running and healthy* but with no network endpoint and none of their published ports, so the pool
guardian could not see a service port and raised critical findings for an hour. `docker restart` does not fix that (the container keeps its empty network settings);
`docker compose up -d --force-recreate --no-deps <service>` does, one container at a time (`docs/runbooks/host-local-config.md`). Another session had already written the sysctl file on the three
0infer VMs at 17:31Z (the 0infer memory-hotplug work, PR #515, writes the same file with the same one-line content and refuses to run over a different one: keep them identical, which is why
the file here has no comment); the other 19 VMs had the same limit and are listed here (docker-runtime, the closest, was using 3.7k of its 7k). A VM whose limit was already right for its size
(postgres-apps-lv3, postgres-replica-lv3: 0.9 GB, runtime-ai-lv3: 1.2 GB) is not listed. The root-cause fix is static memory for such a VM (`qm set <vmid> --hotplug network,disk,usb`,
effective after a cold stop and start); until then this file is the guard. A VM cloned from a template that has memory hot-plug (VM 9000 on 0mcp and on 0infer) starts with the same limit: add every such VM to the manifest when it is
created (or put the file in its cloud-init). The standby DomainScope VM 8101 on 0infer (stopped, never to be started by hand) is a restore of docker-prod's disk and should carry docker-prod's limit;
confirm it the next time it runs.

## Use it

```sh
python3 scripts/hostconf.py check                                    # offline, what CI runs
python3 scripts/hostconf.py drift --all                              # read-only: every host, the baseline, and the guests of every hypervisor; exit 2 = drift, 3 = something could not be looked at
python3 scripts/hostconf.py drift --inventory                        # only the list of guests per hypervisor (unmanaged / gone / stale exemption)
python3 scripts/hostconf.py drift --host webgateway --diff           # with the difference
python3 scripts/hostconf.py apply --host webgateway                  # the plan (no --yes: nothing is changed)
python3 scripts/hostconf.py apply --host webgateway --file sysctl-hotplug-threads-max --yes
python3 scripts/hostconf.py apply --all --file sysctl-hotplug-threads-max --yes   # one host after the other; stops at the first problem
```

It needs the ssh aliases of the manifest and `sudo -n` on the hosts (the tool runs one short python script per host with `sudo -n python3 -`). `apply` writes the new file next to the
old one as `<file>.bak-hostconf-<UTC time>`, writes it atomically (temporary file, fsync, rename), reloads, then checks that every setting of the files it was asked about is in effect; if
not, it puts the old file back, reloads again and exits 5 (4 when even the restore could not be verified: a human must look at once). Exit codes: 0 in sync / applied, 1 refused or invalid,
2 drift or a setting not in effect, 3 a host could not be looked at, 4 rollback not verified, 5 rolled back. `apply` refuses another machine than the one the manifest names
(`hostname`), a file that is a symlink or holds a credential on the host, and a second apply at the same time on one host (flock). An already correct file is not touched; a file that is
right on disk but not loaded (written by hand, never reloaded) is reloaded, not rewritten.

## Add a file

1. Put the content in `files/` (a comment saying why helps whoever finds the file on the host), add a catalog entry to `hostconf.yaml` (`dest`, `src`, `purpose`, `expect`, and `mode`/`group` when not
   0644 root:root) and list its id under the hosts that carry it. `expect` is the proof that the file works: `{systemd: unit, property: P, value: V}` (or `contains:` for a list such as `After`),
   `{sysctl: key, value: V}`, `{pg_setting: name, cluster: 18/main, value: V}`. Quote numbers (`"131072"`). The check cross-reads sysctl and Postgres expectations against the file.
2. `python3 scripts/hostconf.py check`, open a PR, let CI pass, merge, then `drift` and `apply --yes` from a fresh `main`.
3. A file that already exists on a host: add the catalog entry first, then `python3 scripts/hostconf.py adopt --host H --file ID` copies the live file into `files/` byte for byte
   (refused when it holds a credential); review it, `check`, PR. `drift` then proves it is the same.

## Add a host (new VM checklist)

Add it to `hostconf.yaml` with its ssh alias (or none, to go through the guest agent), the name `hostname` prints, and `vm: {hypervisor: <id>, id: <vmid>}` (`sudo: false` when you log in as root and there is no sudo), even when it carries no file: the baseline checks it, and `drift --all` reports the VM as UNMANAGED until you do. A VM below the floor (`cat /proc/sys/kernel/threads-max`; far below `MemTotal_kB / 128` means hot-plugged memory) carries `sysctl-hotplug-threads-max`, a machine above it carries nothing (`drift --all` says which); a nginx or Postgres host carries its restart policy (`OOMPolicy=continue`: without it systemd stops the whole unit when the kernel
OOM-kills one process, and with `Restart=no` nothing starts it again).

## Order and precedence

systemd reads drop-ins in file name order and the last `Key=` wins (list keys such as `After=` add up): `10-` before `20-`. Postgres reads `conf.d` in name order, the last one wins, **and
`postgresql.auto.conf` (written by `ALTER SYSTEM`) beats every conf.d file**. On infer-pg-primary 27 settings (`shared_buffers`, `work_mem`, `max_connections`, the WAL sizes, `primary_conninfo`,
...) come from `postgresql.auto.conf`, while its conf.d files (`90-infer.conf`, `90-domain-scope-standby.conf`, `95-standby-prereqs.conf`) carry older values that were overridden (for example
`90-domain-scope-standby.conf` says `shared_buffers = 30GB` and `90-infer.conf` says `max_connections = 200`; live they are 24GB and 300). That is why `expect` asks the running server, and why those files are not managed here yet: someone who owns the
DomainScope database has to decide which side is right before they are recorded. `log_connections` was set with `ALTER SYSTEM` on 2026-10-19; the `97-log-connections.conf` here is its home, and
`ALTER SYSTEM RESET log_connections` removes the shadow copy. The two `98-` guardrail files of infer-pg-primary (parallel limits, `work_mem`; ADR 0495) are the same case with a *different* value, and there `apply` cannot write them first:
the setting is not in effect while `postgresql.auto.conf` holds the old value, so it puts the file back (exit 5). The order that works is in `docs/runbooks/host-local-config.md`, "Postgres settings that `postgresql.auto.conf` shadows".
A setting that only a restart can change (`huge_pages`, `shared_buffers`) is the same trap in another form: after the reload `SHOW` still returns the running value (`pending_restart` is true) and `apply` never restarts, so it puts the file back (exit 5) while the server runs on the old value. The two huge-pages files of infer-pg-primary
(`sysctl-postgres-hugepages`, which `apply` loads with `sysctl -p` at once and so belongs only on a stopped Postgres, and `postgresql-huge-pages`; ADR 0495) are applied around a restart in a maintenance window: `docs/runbooks/host-local-config.md`, "Huge pages for infer-pg-primary".

## Not managed yet (survey of 2026-10-19; about 125 drop-ins, about 60 sysctl files and 12 Postgres conf.d files on 47 ssh aliases, hash only at first)

The survey found about 125 systemd drop-ins, about 60 sysctl files and 12 Postgres conf.d files outside distro packages (a few machines answer to two aliases and were counted twice). This tool now
holds about 55 of the drop-in and sysctl files plus the Postgres files of 2026-10-19. What is left, and why:

- **Postgres conf.d** (4 files on infer-pg-primary, 8 on the four 0mcp Postgres VMs): the effective values partly come from `postgresql.auto.conf`, see "Order and precedence"; the database owners decide
  first.
- **Credentials**: `caddy.service.d/ntfy.conf` (Hermes VM) and the three `openobserve.conf` drop-ins on the monitoring VM carry tokens inline. The tool refuses them and they must never go in git; they
  need to move to `LoadCredential=` / an `EnvironmentFile=` before they can be recorded.
- **Generated by fleet-runner / CT108 jobs**, which belong in the runner's own templates: `fleet-graph-writer-*` (about 20 drop-ins), `fleet-runner-drift*` (8), `fleet-pool-balance.timer.d/5min.conf`,
  `woodpecker-load-controller@*` (4), `fleet-edge-probe`, `dns-drift-check`.
- **Another release process owns them**: `genfeed-approved-public-crawl-*@.service.d/99-retired.conf` (6, deliberate impossible-condition gates: "a reviewed rollback must replace this drop-in").
- **Provider defaults or stale**: `99-hetzner.conf` and `mdcheck_start.timer.d/hetzner.conf` (Hetzner installimage, 4 hypervisors), `fleet-msg.service.d/observer.conf` (4 hypervisors; fleet-msg was
  retired on 2026-10-17, so these are probably leftovers to delete).

`fleet-state`, `go-fleet-backup` and the registry already hold scripts and service definitions; a deployment's `.env` (the dockerhost fleet-backup NFS options `soft,timeo=200,retrans=3`, see
`docs/runbooks/wedged-host-diagnosis.md`) carries credentials next to its settings and stays out of this tool. `baditaflorin/fleet-edge-hardening` records some of the files managed here (the
node-exporter ordering, the CT108 fstrim skip, Scanopy `FreeBind`) as text plus install notes and has no drift check; `baditaflorin/server-infra-proxmox` and `server-infra-services` are daily
backups of selected live files (nginx `conf.d`, cron, iptables, pve), not a source of truth.
