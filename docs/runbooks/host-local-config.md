# Host-local configuration as code, and the thread limit that broke a container start storm

## Purpose

Say where the configuration that lives only on a host is kept (`config/hostconf/`, applied with `scripts/hostconf.py`), and what to do when a VM with hot-plugged
memory runs out of threads: the failure that left 22 containers of infer-runtime running with no network endpoint after its reboot on 2026-10-19 17:29Z. How the tool works and how to add a
file or a host: `config/hostconf/README.md`.

## Recognise the thread-limit failure

- Right after a reboot (or any burst of container starts) the journal of the Docker host shows, within a second or two, `fork/exec /usr/bin/runc: resource temporarily unavailable`,
  `fork/exec /usr/sbin/iptables: resource temporarily unavailable`, `runtime/cgo: pthread_create failed: Resource temporarily unavailable`, `sshd: error: fork: Resource temporarily unavailable`,
  `(udev-worker): Failed to fork()` and `kernel: workqueue: Failed to create a worker thread: -EAGAIN`. Every process failing at once means a system-wide limit, not a container's.
- Some containers are `running` and `healthy` but have none of their published ports and an empty network (the container was created, its network endpoint was not). Nothing inside them looks wrong;
  from outside the port answers nothing. The pool guardian says `repair_skipped ... no container publishes the service port` and opens `no_redundancy` findings (`FleetPoolGuardianCriticalFinding`),
  the tier-0 edge check counts closed backend ports (`Tier0EdgeBackendPortsClosed`), and nginx keeps the public edge up through the other pool member.
- Rule out a cgroup limit first: `find /sys/fs/cgroup -name pids.events -exec grep -H -v 'max 0' {} +` prints nothing when none was hit. Then compare the limit with what the VM needs:
  `cat /proc/sys/kernel/threads-max` against `cut -d/ -f2 /proc/loadavg` (the number of threads now) and `awk '/MemTotal/ {print int($2/128)}' /proc/meminfo` (what the kernel would have picked
  for this RAM). A limit of about 7000 on a VM with several GB is the hot-plug case: the kernel sized it from the ~1 GB it saw at boot (`qm config <vmid> | grep ^hotplug` on its hypervisor lists `memory`).

## Fix the limit

```sh
python3 scripts/hostconf.py drift --host <id>                       # the file is missing, the setting is not in effect
python3 scripts/hostconf.py apply --host <id> --file sysctl-hotplug-threads-max --yes
```

It writes `/etc/sysctl.d/90-memory-hotplug-threads.conf`, runs `sysctl -p` and checks `sysctl -n kernel.threads-max`; nothing restarts and a running service is not touched.
`python3 scripts/hostconf.py drift --all` also checks the fleet baseline (no machine below 131072 threads, hypervisors included: they pass on their own boot default and need no file) and prints
`BELOW BASELINE` for any that is under; a new VM from the Ansible role's cloud-init template already has the file. The same command lists every guest of the five hypervisors and reports `UNMANAGED` for a VM nobody added to the
manifest (a clone made by hand, a restore): add it with its `vm:` and, if it is below the floor, the file; `GONE` and `STALE EXEMPTION` mean the manifest is out of date. A VM that is not in
the manifest yet: add it (`config/hostconf/README.md`, "Add a host"). By hand, as a stop gap: `sudo sysctl -w kernel.threads-max=131072` (lost at the next boot: add it to the manifest afterwards).

## Repair the containers that came up without a network endpoint

`docker restart` does not help (the container keeps its empty network settings), and neither does waiting. Recreate each one from its own compose files, one at a time, so the repair does not
recreate the storm. Find them on the Docker host:

```sh
sudo docker ps -q | xargs sudo docker inspect --format '{{.Name}} {{.HostConfig.NetworkMode}} {{len .HostConfig.PortBindings}} {{len .NetworkSettings.Ports}} {{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
  | awk '$2 != "host" && $2 != "none" && $2 !~ /^container:/ && ($3 > 0 && $4 == 0 || NF < 5) {print $1}'
```

(declared ports but none published, or no IP address; a leftover container of an old compose project whose port is taken by its replacement shows up too: check its labels before recreating it). For each name `c`: read `com.docker.compose.project.working_dir` and `com.docker.compose.service` from its labels
(`docker inspect c --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}} {{index .Config.Labels "com.docker.compose.service"}}'`), then

```sh
cd <working_dir> && sudo docker compose up -d --force-recreate --no-deps <service>
```

and check that `docker ps --filter name=^c$ --format '{{.Ports}}'` shows the published port again and that the endpoint answers from where its callers are (for the infer-runtime pool replicas that is the
gateway, `curl http://<tailnet ip>:<port>/health`, not the builder: the tailnet ACL lets only the gateway in). Same image, same configuration; the compose project is the source of truth.
On 2026-10-19 this took 22 containers about 3 minutes, one by one, with a 3 s pause between them.

## After

- `python3 scripts/hostconf.py drift --all` is clean.
- The guardian's findings clear in its next run (it takes 20-30 minutes); `systemctl start tier0-edge-compat.service` on infer-tier0 refreshes `tier0_runner_edge_compat_backends_closed` at once (it only reads),
  otherwise the hourly timer does.
- The root cause of the small limit is the VM's `hotplug` option including `memory`: with static memory the kernel sizes the limit from the real RAM at boot. `qm set <vmid> --hotplug network,disk,usb` takes
  effect after a cold stop and start, so it waits for a maintenance window; the manifest is the guard until then.

## Postgres settings that `postgresql.auto.conf` shadows (infer-pg-primary: the two guardrail files of ADR 0495)

Postgres reads `conf.d` in name order and then `postgresql.auto.conf`, which `ALTER SYSTEM` writes and which **beats every conf.d file**. On infer-pg-primary `max_parallel_workers_per_gather` (4), `max_parallel_workers` (24) and `work_mem` (256MB) are `ALTER SYSTEM` values today (`temp_file_limit` is at its default, -1, and probably not in that file). The two files `postgresql-parallel-guardrails.infer-pg-primary` (`98-parallel-guardrails.conf`: 4, 12, 150GB) and
`postgresql-work-mem-guardrails.infer-pg-primary` (`98-work-mem-guardrails.conf`: 64MB) therefore do nothing until the `ALTER SYSTEM` entries are reset, and `hostconf.py apply` cannot write them first: it reloads, reads each
`expect` back with `SHOW`, finds the old value, puts the old file back and exits 5. Merging the PR changes no host: `drift --host infer-pg-primary` reports both files missing and their settings not in effect until they are
applied, and `HostconfDrift` fires when the daily check still sees it on the second run, so apply within a day. Two files on purpose: apply the parallel file first, the `work_mem` file 30 minutes later, one reload each, so a regression is
attributable to one knob (preconditions, acceptance numbers and the maintenance rules: ADR 0495; claim VM701 in `fleet-ctx` first). Do the steps below for **one file at a time**, from a fresh `main`. The SQL runs as the `postgres` user (`sudo -u postgres psql -X`) and is meant to be piped in on stdin, which sends each statement on its own: a single `psql -c 'a; b'` is one multi-command string and `ALTER SYSTEM` refuses it.

1. **Look, then back up.** Read-only first: `SELECT name, setting, unit, source, sourcefile FROM pg_settings WHERE name IN ('max_parallel_workers_per_gather','max_parallel_workers','temp_file_limit');` (or `'work_mem'`) and keep the output: it is the before state, and `source = 'configuration file'` with `sourcefile` ending in `postgresql.auto.conf` marks a shadowed name
   (a name that is not there is harmless in steps 2 and 4, which keep the three steps the same for every name). Then back up `postgresql.auto.conf` (next to it, as for `pg_hba.conf`): `sudo -u postgres sh -c 'd=$(psql -XAtc "SHOW data_directory") && cp -p "$d/postgresql.auto.conf" "$d/postgresql.auto.conf.bak-$(date -u +%Y%m%dT%H%M%SZ)"'`. Keep the name: the rollback uses it.
2. **Make the shadow copy carry the new values and reload**, so that the live value and the file agree when `apply` looks (this is the one reload that changes behaviour; it is exactly the reload the file will repeat). For the parallel file:
   `ALTER SYSTEM SET max_parallel_workers_per_gather = 4; ALTER SYSTEM SET max_parallel_workers = 12; ALTER SYSTEM SET temp_file_limit = '150GB'; SELECT pg_reload_conf();`
   for the `work_mem` file: `ALTER SYSTEM SET work_mem = '64MB'; SELECT pg_reload_conf();`. `SHOW` each name and compare with the file before going on. Do not `RESET` first: until the file exists the setting would fall back to the next source (an older conf.d file or the built-in default, 4MB for `work_mem`).
3. **Apply the file**: `python3 scripts/hostconf.py apply --host infer-pg-primary --file postgresql-parallel-guardrails.infer-pg-primary --yes` (or `postgresql-work-mem-guardrails.infer-pg-primary`). It writes `/etc/postgresql/18/main/conf.d/98-...conf`
   (0640, group `postgres`), reloads the cluster and checks the settings; `status: applied`, exit 0. Nothing is restarted and `pending_restart` stays empty (none of these settings needs a restart).
4. **Remove the shadow copy and reload**: `ALTER SYSTEM RESET max_parallel_workers_per_gather; ALTER SYSTEM RESET max_parallel_workers; ALTER SYSTEM RESET temp_file_limit; SELECT pg_reload_conf();` (the `work_mem` file: `ALTER SYSTEM RESET work_mem;`).
   The value does not change; it now comes from the file. This is what was done for `97-log-connections`.
5. **Verify**: `SELECT name, setting, unit, source, sourcefile, pending_restart FROM pg_settings WHERE name IN ('max_parallel_workers_per_gather','max_parallel_workers','temp_file_limit');` (or `'work_mem'`): `source` is `configuration file`, `sourcefile`
   ends in `/conf.d/98-parallel-guardrails.conf` (`98-work-mem-guardrails.conf`), `pending_restart` is false. `grep -c` of the names in `postgresql.auto.conf` is 0 for the ones moved, and `python3 scripts/hostconf.py drift --host infer-pg-primary` exits 0.

**Changing a value later.** Once a name has been moved (S1, 2026-11-01), the file is its source and nothing shadows it, so a later change of the value is a plain `apply`, without the steps above: edit the file in a PR, merge, then
`python3 scripts/hostconf.py apply --host infer-pg-primary --file postgresql-parallel-guardrails.infer-pg-primary --yes` (reload only; `SHOW` agrees, so `apply` keeps it). Look at `pg_settings.source` and `sourcefile` first: if `sourcefile` still names `postgresql.auto.conf`, use the steps above.
The first use was `max_parallel_workers_per_gather` 2 -> 4 (ADR 0495, amendment of 2026-11-02): the 24 h acceptance of S1 found `SELECT COUNT(*) FROM mv_domains_denormalized` 48 % slower with half the workers per call, so that one knob went back and `max_parallel_workers` (12), `temp_file_limit` (150GB) and the `work_mem` file stayed.
Its rollback is the file back to 2 and one more `apply`.

Rollback of a step, fastest first: `ALTER SYSTEM SET` the old values back (4, 24, `-1`, `256MB`; they beat the file and take effect on `pg_reload_conf()`), or put the `postgresql.auto.conf.bak-<UTC>` of step 1 back over `postgresql.auto.conf` as `postgres` and reload.
`hostconf.py` never deletes a file it has applied, so a rolled-back file stays on the host (shadowed, so harmless) until the entry is removed from `hostconf.yaml` in a PR and the file is removed by hand; until then `drift` reports the setting not in effect, which is the reminder.
The same order applies to any later conf.d file that records a setting `postgresql.auto.conf` already holds with a different value; when the values are equal (as `log_connections` was) steps 1 and 2 are not needed. Huge pages are not part of this: they are a separate change,
applied only in a maintenance window (applying a sysctl file runs `sysctl -p` at once, and `huge_pages = on` needs a restart). The `/dev/shm` cap and the VM memory are in `config/0infer/pg-primary-memory/`.

## Huge pages for infer-pg-primary (ADR 0495, S2: planned 2026-11-04, 11:00-12:00Z)

Two files, `sysctl-postgres-hugepages.infer-pg-primary` (`/etc/sysctl.d/91-postgres-hugepages.conf`: `vm.nr_hugepages = 12800`) and `postgresql-huge-pages.infer-pg-primary` (`conf.d/99-huge-pages.conf`: `huge_pages = on`), reserve 25.0 GiB of 2 MiB pages for the 24.66 GiB shared-memory segment
(`shared_memory_size_in_huge_pages` 12628; the 172 extra pages are 344 MiB of margin) and take the per-backend page tables from 43-48 MiB to about 0.1 MiB. **Merging applies nothing**: the PR is merged only just before the window, and until the files are applied the daily `drift --all` reports both as missing
(`HostconfDrift` fires on the second daily check, so never leave them unapplied for days). Window: **planned 2026-11-04, 11:00-12:00Z (any day 11:00-13:00Z once S1c has run 24 h)**, one restart, 60 s budget for the outage (5 s measured on 2026-10-30). Claim VM701 in `fleet-ctx` first. Two behaviours of `hostconf.py` decide the order, so read them before the steps:

- **A sysctl file is applied with `sysctl -p` at once.** Apply it only with Postgres stopped: reserving while it runs counts the resident 24.6 GiB segment twice and evicts about 25 GiB of page cache (only about 0.2 GiB of free 2 MiB blocks exist). The tool wants exactly 12800: if the kernel reserves fewer, `apply` finds the setting not in effect, takes the file and the old page count back and exits 5, so a short
  reservation is no reservation. A script that drives these steps must not stop at that exit with Postgres down: the next action is the compaction retry or the fallback.
- **`huge_pages` needs a restart**, and `apply` never restarts. After a reload `SHOW huge_pages` still says `try` (`pending_restart` is true), so `apply` of `99-huge-pages.conf` while the server runs on `try` reads `try`, puts the file back and exits 5. The order below therefore seeds the value with `ALTER SYSTEM` before the stop (a restart setting: nothing changes until then) and applies the
  file after the start, when `SHOW` already says `on`; it is the same seed, apply, reset sequence as "Postgres settings that `postgresql.auto.conf` shadows". Ballooning must stay off while pages are reserved (`balloon` equals `memory` on VM701, 66560 MiB). SQL runs as `postgres` and is piped in on stdin (`ALTER SYSTEM` refuses a multi-command string).
- **Rider: `pg_stat_statements.max` 5000 -> 20000** (`postgresql-pgss-max.infer-pg-primary`, `conf.d/99-pgss-max.conf`) is a restart setting of a preloaded library, so it follows the same order as `huge_pages` and rides on the same restart: `apply` before the restart reads `5000` and exits 5, so the value is seeded with `ALTER SYSTEM` before the stop and the file is applied after the start, when `SHOW` says `20000`. It costs about 6 MB of shared memory (about 3 of the 172 spare huge pages) and the clean shutdown keeps the statistics file, so the next 24 h of `pg_stat_statements` are complete (it evicted its 5,000 entries 2,000+ times and attributes only 3.8 GB of the 612 GB of temporary files).

1. **Preflight, read-only.** Inside 11:00-13:00Z; `SHOW huge_pages` is `try` and `SHOW pg_stat_statements.max` is `5000`; `SHOW shared_memory_size_in_huge_pages` is 12628 (not above 12800); `HugePages_Total` is 0; `MemAvailable` is above 25 GiB; no base backup (`pg_stat_progress_basebackup`), no standby rehearsal, no hand job on VM101 or CT108; the replica streams; `qm config 701` shows `balloon` equal to `memory`; the two S1 files and S1c (the per-gather change of the amendment of 2026-11-02) have run 24 h with their acceptance numbers;
   `python3 scripts/hostconf.py drift --host infer-pg-primary` names exactly the three new files (the two huge-pages files and `postgresql-pgss-max.infer-pg-primary`) as missing and nothing else.
2. **Back up and seed.** Back up `postgresql.auto.conf` exactly as in step 1 of the section above (keep the name), then, as two statements piped in on stdin, `ALTER SYSTEM SET huge_pages = 'on';` and `ALTER SYSTEM SET pg_stat_statements.max = 20000;`. Nothing is reloaded and nothing changes: `SHOW` stays `try` and `5000` (`pending_restart` turns `t` at the next reload). Do not apply `99-huge-pages.conf` or `99-pgss-max.conf` yet (exit 5, see above).
3. **`CHECKPOINT;` twice.**
4. **Stop**: `systemctl stop postgresql@18-main`; no `postgres` process is left. The outage starts.
5. **Reserve**: `python3 scripts/hostconf.py apply --host infer-pg-primary --file sysctl-postgres-hugepages.infer-pg-primary --yes`. Then `HugePages_Total` in `/proc/meminfo` must be 12800 (12628 is the least that lets `on` start). Exit 5 means nothing was reserved and the file was taken back: `echo 1 > /proc/sys/vm/compact_memory`, apply once more; still short: the fallback below.
6. **Start**: `systemctl start postgresql@18-main`. With `huge_pages = on` it does not start if the pages are not there (the journal says it could not map the shared memory): the fallback below, at once.
7. **Verify, outage over** (write down the seconds): `SHOW huge_pages` is `on`, `SHOW huge_pages_status` is `on`, `SHOW pg_stat_statements.max` is `20000` and `SELECT count(*) FROM pg_stat_statements` is not 0 (the clean shutdown kept the statistics file); `pg_is_in_recovery()` is false; the public `/health` answers 200; the replica streams; in `/proc/meminfo` `HugePages_Free` is about 169 to 172 (the rider takes about 3 pages), `Shmem` about 0.05 GiB, `PageTables` under 0.5 GiB.
8. **Make it durable**: `python3 scripts/hostconf.py apply --host infer-pg-primary --file postgresql-huge-pages.infer-pg-primary --yes`, then the same with `--file postgresql-pgss-max.infer-pg-primary --yes` (the settings read `on` and `20000` now, so each passes: `applied`, exit 0, nothing pending), then `ALTER SYSTEM RESET huge_pages; ALTER SYSTEM RESET pg_stat_statements.max; SELECT pg_reload_conf();` (separate statements on stdin) and check `pg_settings` for both: `source` is `configuration file`, `sourcefile` ends in `/conf.d/99-huge-pages.conf` and `/conf.d/99-pgss-max.conf`, `pending_restart` is false
   (the running values do not change). `python3 scripts/hostconf.py drift --host infer-pg-primary` exits 0.
9. **After**: `domainscope-prewarm` acts 5 minutes after the start (100 MB/s, about 4 minutes for 24 GiB; the page cache is kept); read the log for errors; note the numbers of step 7 in ADR 0495.

**Fallback** (the reservation is short after one retry, or the start with `on` fails): with Postgres stopped, put the `postgresql.auto.conf` backup of step 2 back (`huge_pages` is `try` and `pg_stat_statements.max` 5000 again: both seeds were made after that backup, so one restore covers both), start, and check that it serves. None of the files stays on the host (the sysctl `apply` took itself back and `99-huge-pages.conf` and `99-pgss-max.conf` were never written); the rider waits for the next restart. Reserve later at a planned reboot with the kernel parameter `hugepages=12800`
(or repeat steps 4-8 in another window): a sysctl file also reserves at boot, but `hostconf.py` does not keep one that could not reserve everything at apply time. Until then Postgres runs as before the window.

**Rollback** (after the start, about 30 s): stop; `sysctl -w vm.nr_hugepages=0` and move `/etc/sysctl.d/91-postgres-hugepages.conf` aside so the pages are not reserved at the next boot; set `huge_pages` back to `try` (restore the step 2 backup before step 8; after it edit the line in `99-huge-pages.conf`, which `drift` then reports as differing); start; verify it serves. Remove the two huge-pages entries from `hostconf.yaml` in a PR afterwards (`hostconf.py` never deletes a file). The rider needs no rollback for the pages: `pg_stat_statements.max = 20000` is harmless on its own; to undo it too, remove `99-pgss-max.conf` and its entry, and the next restart reads 5000.

## The scheduled check and its alerts

Once a day (12:20 local) a LaunchAgent on the operator's machine runs `scripts/hostconf-scheduled.sh run`: it takes `scripts/hostconf.py` and `config/hostconf/` from main, runs `drift --all` (read-only) and writes the
result to the monitoring VM as `/var/lib/prometheus/node-exporter/fleet_hostconf.prom` (renamed into place, so node_exporter never reads half a file). `scripts/hostconf-scheduled.sh install` copies the script to
`~/.local/share/hostconf-drift/`, writes `~/Library/LaunchAgents/org.baditaflorin.hostconf-drift.plist`, makes the first checkout and loads the agent; `uninstall` removes both; `status` shows the agent, the last log
lines (`~/Library/Logs/hostconf-drift.log`) and when the file on the monitoring VM was written; `launchctl kickstart gui/$(id -u)/org.baditaflorin.hostconf-drift` runs it now. The file keeps its last values between
runs, so the alerts' `for:` counts runs: 2 h is "still there at the next look", 26 h is "there on two daily runs in a row". All are warnings; the rules are `config/prometheus/rules/fleet-hostconf.yml`.

| Alert | It means | What to do |
| --- | --- | --- |
| `HostconfBelowBaseline` | the machine's `kernel.threads-max` is under 131072, or its floor file is listed and not applied | "Fix the limit" above: `drift --host <machine>`, then `apply --host <machine> --file sysctl-hotplug-threads-max --yes`; add `sysctl-hotplug-threads-max` to the machine in `hostconf.yaml` if it is not listed |
| `HostconfDrift` | a managed drop-in, sysctl or Postgres file differs from the repo, or a setting is not in effect (a machine under the floor is reported by the alert above only) | `drift --host <machine> --diff`; either adopt the host's version into the repo (`adopt`) or apply the repo's |
| `HostconfInventoryFinding` | a hypervisor runs a guest the manifest does not know (UNMANAGED), or the manifest lists a machine that is gone | `drift --inventory`; add the guest ("Add a host" in `config/hostconf/README.md`, with its `vm:`) or remove the machine from the manifest |
| `HostconfMachineUnreachable`, `HostconfInventoryUnreachable` | the check could not look at a machine, or list a hypervisor's guests, on two daily runs in a row | `drift --host <machine>` or `drift --inventory` shows the ssh or `pvesh` error; a machine nobody can look at is a machine nobody checks |
| `HostconfCheckStale` (36 h), `HostconfCheckMissing` | the job has not delivered: the operator's machine was off or asleep for two days, its ssh keys were not available to the job (locked keychain, rotated key), the manifest on main is invalid (`python3 scripts/hostconf.py check`) or the monitoring VM refused the write | `scripts/hostconf-scheduled.sh status` and the log on the operator's machine; `scripts/hostconf-scheduled.sh run` by hand shows the error |

Trust and limits, plainly: the job runs unattended with the operator's ssh access, so it is built to be unable to change anything. It runs only `drift` (a test fails if the script runs `apply` or `adopt`), the remote script
in observe mode writes nothing, and the only thing it runs with `sudo` is writing the one metrics file on the monitoring VM. It executes the tool from main, so main is the trust boundary, the same one every reviewed
change to this repository already crosses. It depends on one machine being on, which is why a missing result is an alert of its own. A second operator machine can run the same job (the file is overwritten by whoever
ran last); the builder cannot until it has ssh access to these hosts, which is a wider grant than this check needs. Found 2026-10-20: VM 705 (`infer-spire`, a SPIRE server restored on 0infer) ran for hours with a 15,590
thread limit because the only check was run by hand.

## Related

`config/hostconf/README.md` (the tool, the manifest and what is not managed yet), `docs/adr/0495-pg-primary-memory-guardrails.md` and `config/0infer/pg-primary-memory/README.md` (the VM701 memory guardrails), `docs/runbooks/wedged-host-diagnosis.md` (a different way a Docker host stops), `docs/runbooks/fleet-observability.md` (alerts).
