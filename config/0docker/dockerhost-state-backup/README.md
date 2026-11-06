# dockerhost-state-backup: file-level backup of the Docker host (VM 100) to own-pbs

Installed on the 0docker Docker host VM (`ubuntuvm1`, 10.10.10.20, tailnet 100.64.0.7, Ubuntu 24.04). The VM is not managed by Ansible or
fleet-runner, so this directory is the source of truth: change a file here through a PR, then install it as below.

## Why this exists
The VM-level backup of VM 100 (vzdump snapshot, job `fleet-vm100-nightly`) has been **paused since 2026-10-19 08:25Z**. Three attempts hurt the
host: a slow PBS stalled the guest through copy-before-write, a fast one caused a run-queue explosion (load 455 to 722 in four minutes), and a
capped run with fleecing filled the hypervisor's root filesystem (the only storage; 86 % full). The newest VM-level restore point is
`0docker/vm/100/2026-10-18T02:07:28Z`. This job takes its place: it reads the guest's own files from inside the guest, at idle priority, so the hypervisor
does nothing and there is no copy-before-write. (`0docker/vm/100` stays in PBS as the old VM-level copy; nothing here touches the paused job.)

## What one run does (nightly 17:30Z, `dockerhost-state-backup.timer`)
1. Preflight: client installed, token file private (0600, root), the 5-minute load average at or under `start_load5` (waits up to 30 minutes, then skips and says so).
2. Stages what a plain file copy gets wrong, under `/var/backups/dockerhost-state` (removed after the run):
   * `pg/<container>.sql.gz`: `pg_dumpall --clean --if-exists` of **every running Postgres container** (found by the `/var/lib/postgresql/data` mount, so it follows new ones), as the container's own `POSTGRES_USER`;
   * `sqlite/<original path>`: an **online copy** (sqlite3 backup API, source opened read-only) of every SQLite database that is open right now. All the big ones are WAL-mode with hundreds of MB of
     un-checkpointed WAL (graph.db, chaos.db, kuma.db, keys.db, grafana.db): a plain file copy of the main file alone loses those rows and a copy of file plus WAL taken at two moments can be torn.
     The copies are made **one at a time, largest first**, and a copy of 64 MiB or more becomes `sqlite/<original path>.zst` before the next one starts (the Staging peak bullet below);
   * Each SQLite copy is followed by a separate `quick_check` of the copy (its own child process, `check_timeout_s` 3600): the copy has its own limit `sqlite_timeout_s` (3 h) and decides success; the check
     only tells whether the SOURCE was already damaged. It never discards a finished copy: a check that does not finish in time is a note, a damaged source is a warning with the copy kept. (2026-10-21: chaos.db,
     8.7 GB, took over an hour on the CPU-starved host, and a single 1 h limit over copy plus check threw away a complete copy.)
   * The check is skipped for staged copies above `check_max_bytes` (512 MiB): on the CPU-starved host it needed 51 min for kuma.db (2.5 GB) and ran into its 1 h limit for graph.db and chaos.db, which stretched a
     24-minute upload to a 3 h 44 min run on 2026-10-22. The copy of those databases is still complete and consistent (a single read snapshot of the source); only the "was the source already damaged" look is dropped for them.
   * **Staging peak** (since 2026-10-29, numbers in the section of that name): a copy of `limits.compress_min_bytes` (64 MiB) or more is compressed with `zstd -1` into `<name>.zst` right after its copy (and its
     `quick_check`, when it is small enough to get one). The compressed file is then read back through `zstd -d` and its sha256 compared with the raw copy's, and only then is the raw copy deleted and the disk
     blocks it held trimmed (FITRIM of exactly its extents, after an fsync of the directory that forces the journal commit ext4 needs before it offers a freed block). So the staging directory holds one raw copy
     at most, not all of them. If anything goes wrong (zstd missing, a timeout, a mismatch) the raw copy stays, the run says so in a warning and ends failed (`DockerhostStateBackupFailed`), and the backup is
     still complete: the peak is then higher by that copy. A self-test before the first copy (32 MiB written, deleted, trimmed) checks that trimming works here; if not, the run stages as before, all at once, and says so the same way. `MANIFEST.json` says per copy what was staged (`staged`, `codec`, `copy_bytes`, `staged_bytes`, `sha256` of the raw copy) and the run's `staging_peak_bytes`.
   * `inventory/`: 23 small text files. The first 11 are `docker ps -a`, images, `docker volume inspect` of every volume, networks, packages, enabled units, root crontab, df, lsblk, addresses and `uname`; they read
     no environment variables (those hold secrets). The last 12 are "what a rebuild needs and a file copy does not carry", added on VM 100 by hand on 2026-10-29 and in git since 2026-10-30 (section "Added on VM 100
     on 2026-10-29"). Every entry only reads. One that fails or whose program is missing (no `tailscale`, no `nft`) leaves a `# command failed` note in its own file and does not stop the run.
3. One `proxmox-backup-client backup` call, so **one snapshot** `host/dockerhost-state/<time>` in namespace `0docker` holds the archives `etc`, `opt`, `home`, `srv`, `root`, `volumes`, `usr_local`, `tailscale`,
   `dockernet`, `systemd_state`, `url_categorizer_state`, `fleet_container_audit` (the last six since 2026-10-29) and `staging`
   (`--change-detection-mode metadata`: unchanged files are not read again; `--crypt-mode none`, see Limits).
4. Writes `/var/lib/prometheus/node-exporter/dockerhost_state_backup.prom` and exits non-zero on any failure or warning.

## What is left out, and why
| Left out | Why |
|---|---|
| data dirs of the dumped Postgres containers | a live file copy of a Postgres data directory is not restorable; the dump is |
| live SQLite files and their `-wal`/`-shm`/`-journal` | the staged online copy is in `staging.pxar` |
| data dirs of running Elasticsearch containers | search indexes, rebuilt from their database |
| `volumes/fleet-backup_backup-destination` | the NFS destination of the existing `fleet-backup` service (already off-host on the 0own hypervisor) |
| `volumes/buildx_*_state`, `0init-komodo-repo-cache`, `root/embcache` (8.3 GB), `root/.cache`, `root/go`, `root/build_scratch` | caches that are rebuilt |
| `volumes/metadata.db`, `backingFsBlockDev` | Docker's own bolt database (its content is in `inventory/docker-volumes.json`) and a device node |
| `etc/dockerhost-state-backup/token.secret` | the backup must not carry its own token |
| `usr_local/bin/cosign` (135 MB) | a release binary of the signing tool, downloaded again when needed |
| Docker images, containers, overlay2, `/var/log`, `/usr` (apart from `/usr/local`), `/boot` | rebuildable from the compose files in `/opt` and the package list |

SQLite files that match `raw_sqlite` in `config.json` are copied as they are, never staged and never a warning: static copies and known-corrupt recovery copies (`/srv/hermes-offsite/backups/*` and
`recovery-work-*`, the keystore's `data/backups/*` and `promote-*`, the credential broker's snapshots). They have a leftover `-shm` so they look open, the two recovery copies are damaged on purpose to keep,
and an online copy of a half-written broker snapshot fails ("attempt to write a readonly database"). A database with a virtual table this Python's sqlite cannot open (hermes `state.db`:
`messages_fts_trigram`) is copied online but not `quick_check`ed ("copied, not checked" in the log). Each staged copy is converted to a rollback-journal file so no `-wal`/`-shm` travels with it.
Anything else whose online copy fails stays in the file archive (a raw copy of a live WAL database can be torn: that is why the run then ends failed and `DockerhostStateBackupFailed` fires).

Redis and ClickHouse files are copied as they are (crash-consistent: the same quality as the old VM-level backup). The existing `fleet-backup` service (secrets-db, keystore-db, broker-db
snapshots as `.age` archives to NFS and a private GitHub repo) is separate and stays; the keystore also has five mesh nodes.

## Added on VM 100 on 2026-10-29 (in git since 2026-10-30)
On 2026-10-29 someone extended the installed script (20:48Z) and config (21:01Z) on VM 100 by hand with "what a rebuild needs and a file copy does not carry". Neither change was in a PR, and the next install from git
would have dropped them. This directory has them since 2026-10-30, exactly as they run: nothing was added, removed or reworded. The author is not recorded (the sudo log shows only the shared `ubuntu_vm` account), so the
purposes below are read from what each one holds. Sizes are from VM 100 on 2026-10-30.

**12 inventory entries** (`inventory/<file>` in the staging directory, about 1.2 MB together before compression):

| File | Command | What it holds | Size |
|---|---|---|---|
| `os-release.txt` | `cat /etc/os-release` | the Ubuntu release | 0.4 KB |
| `docker-version.txt` | `docker version; docker compose version` | engine and compose plugin versions | 0.8 KB |
| `docker-images-digests.txt` | `docker images --digests` | repository, tag, digest and id of the 232 images | 27 KB |
| `docker-networks-inspect.json` | `docker network ls -q \| xargs -r docker network inspect` | subnets, gateways and attached endpoints of the 241 networks | 570 KB |
| `docker-compose-ls.txt` | `docker compose ls -a` | the compose projects, their state and config files | 74 KB |
| `docker-noncompose-containers.json` | `docker ps -aq \| xargs -r docker inspect --format ... \| awk 'NF==1{print $1}' \| xargs -r docker inspect` | meant to be the full `docker inspect` of every container no compose project started | **0 bytes**, see Known issue |
| `nft-ruleset.txt` | `nft list ruleset` | the nftables rules, Docker's included | 267 KB |
| `iptables-save.txt` | `iptables-save` | the iptables rules | 205 KB |
| `ip-route.txt` | `ip route` | the routing table (a route per Docker network) | 19 KB |
| `hostnamectl.txt` | `hostnamectl` | hostname, machine id, kernel, virtualisation | 0.5 KB |
| `tailscale-status.txt` | `tailscale status` | the tailnet peers and their addresses | 7 KB |
| `systemd-timers.txt` | `systemctl list-timers --all --no-pager` | every timer with its last and next run | 5 KB |

All twelve only read; all exist on VM 100 for root with the service's default PATH and exit 0 (checked 2026-10-30: 3 seconds in all).

**6 archives** (`config.json`), after `volumes` and in this order (the order of the client's arguments):

| Archive | Path | Size | What it holds |
|---|---|---|---|
| `usr_local` | `/usr/local` | 65 MB (200 MB less the excluded `bin/cosign`, 135 MB) | local scripts (`bin`, `sbin`, `libexec`: the container audit, the Docker GC, the SPIRE and proxy checks, ...), the release binaries `scanopy-daemon` (42 MB), `periphery` (17 MB) and `websocat`, and the saved `dockerhost-state-backup.pre-*` copies of this script |
| `tailscale` | `/var/lib/tailscale` | 21 KB | the node's identity (`tailscaled.state`) and its tailnet-lock data |
| `dockernet` | `/var/lib/docker/network` | 4 MiB | `files/local-kv.db`, libnetwork's database of networks, endpoints and address allocations (a bolt file dockerd has open: a crash-consistent copy, like Redis) |
| `systemd_state` | `/var/lib/systemd` | 235 KB | `catalog`, `deb-systemd-helper-enabled` (175 small files), the 13 stamp files of persistent `timers`, `timesync`, and two secret files (below); no core dumps |
| `url_categorizer_state` | `/var/lib/url-categorizer` | 131 MB | `geoip/GeoLite2-City.mmdb`, the MaxMind city database of the url-categorizer |
| `fleet_container_audit` | `/var/lib/fleet-container-audit` | 1.3 MB | `services.json`, the container audit's catalogue of 533 services (names, URLs, tags, TRL fields; no environment values) |

A `/var/spool/cron` archive was tried on 2026-10-29 and removed again: the run failed at 21:00Z with `unable to access '/var/spool/cron' - No such file or directory` (the directory does not exist on VM 100; root's crontab is
in `inventory/crontab-root.txt`).

**What these put in the snapshot in clear text** (looked at on VM 100 on 2026-10-30: file names, modes, sizes and counts only; no secret value was read into this file or the pull request):
* `tailscale`: `tailscaled.state` (0600) holds the node's private keys. Whoever can read the snapshot can act as VM 100 (100.64.0.7) on the tailnet inside the grants that address has, and a restore onto a second VM
  while this one runs makes two nodes with one identity.
* `systemd_state`: `credential.secret` (0400, 4,112 bytes) is systemd's host key for `systemd-creds`, and `random-seed` (512 bytes) is this machine's entropy seed, which must never be cloned onto another one. VM 100 has no
  TPM (`systemd-creds has-tpm2` says `-firmware -driver`). `/etc/credstore.encrypted`, in the `etc` archive of the same snapshot, holds two encrypted admin tokens (`apikey-service-admin-token.cred`,
  `fleet-secrets-admin-token.cred`): if they are host-key credentials, as their place suggests, the key now travels with them. Everything else in that archive (the 223 KB `catalog`, the enabled-unit links, the
  timer stamps) can be regenerated.
* `usr_local`: a scan of its text files for password, secret, token and key words (file names only) matched 15 files: this script and its five saved copies (they name `PBS_PASSWORD`) and 9 other scripts that mention them.
  None of the current scripts assigns a literal credential (the one literal-looking assignment, `APIKEY_ADMIN_FILE` in `bin/apikey`, is the default path of an `.env` file); the saved copies and the `scanopy-daemon` binary were not checked
  one by one. Six files are root-only (0700): `scanopy-daemon`, `enrichment-composition-route`, `fetch-cache-html-route`, `fetch-cache-render-route` with its `.before-html` copy, and a saved `go-html-proxy-approve`;
  their owner should look at them.
* `dockernet`, `url_categorizer_state` and `fleet_container_audit`: nothing found. `docker-noncompose-containers.json`: nothing today, see the next paragraph.
* Since when: on 2026-10-30 15:46Z the only snapshot on own-pbs with the six archives is `2026-10-29T21:13:46Z` (the manual run of 21:01Z; the nightly one of 19:49Z has the old seven), and PBS #2 should have it too
  (`pull-0docker` takes the newest two). Leaving a file out later does not remove it from them: they stay until `prune-0docker` ages them out or someone forgets them by hand.

**Known issue: `docker-noncompose-containers.json` is always empty.** `docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}'` prints `<no value>` for a container without that label, so its line is
`<id> <no value>`, three fields, and `awk 'NF==1'` drops it. Five of the 458 containers have no compose label (`buildx_buildkit_remote0`, `bwa-live`, `bwa-hr-live`, `bwa-storyline`, `veld-moodboard`) and none of them reaches the
file (checked 2026-10-30; `tests/test_dockerhost_state_backup_staging.py` pins it). That is also what keeps container environment variables out of the snapshot today: a working filter would write the full `docker inspect`
of those five (about 32 KB), including `Config.Env`: 36 variables each for `bwa-live` and `bwa-hr-live`, 11 of them with secret-looking names (a Supabase service-role key and a Replicate token among them). The script's
own rule (`containers()`: "no environment: it holds secrets") and the `inventory/` bullet above say the environment is never stored. So fix the filter and the environment together: print the variable names only, or encrypt
the snapshot (see Limits and decisions).

**Live and git.** `/usr/local/sbin/dockerhost-state-backup` and `/etc/dockerhost-state-backup/config.json` are copies of the two files here (Install). On 2026-10-30 the script on VM 100 was byte-identical to
`dockerhost_state_backup.py`, and the config equal to `config.json` apart from whitespace, key order and four keys the host's copy does not have (`limits.compress_min_bytes`, `limits.compress_timeout_s`, `limits.trim_wait_s`
and `trim_staging`, from the staging change): the script's defaults for them are the values in this file, so the host behaves the same and the next install adds them. Compare before every install, and put a change made on
the host into a pull request the same day:
```
sha256sum dockerhost_state_backup.py; ssh 0docker_docker 'sha256sum /usr/local/sbin/dockerhost-state-backup'
canon() { python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin), indent=1, sort_keys=True))'; }
diff <(ssh 0docker_docker 'sudo cat /etc/dockerhost-state-backup/config.json' | canon) <(canon < config.json)
```

## Install (as root on VM 100; every step keeps a backup of what it replaces)
```
install -d -m 0700 /etc/dockerhost-state-backup
install -m 0755 dockerhost_state_backup.py /usr/local/sbin/dockerhost-state-backup
install -m 0644 config.json /etc/dockerhost-state-backup/config.json
install -m 0644 dockerhost-state-backup.service dockerhost-state-backup.timer /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now dockerhost-state-backup.timer
```
Prerequisites (done 2026-10-21): `proxmox-backup-client` 3.4.9 (Proxmox's own package, taken from the 0docker hypervisor's apt repo, sha256 `edf7c26a4eb84272936092c423e3f89a5b2fd9d64d1876447e19c14644c0322d`, plus Ubuntu's `qrencode`);
the tailnet grant `100.64.0.7 -> own-pbs tcp:8007` (config/tailscale/policy.hujson); on own-pbs the user `backup-dockerhost@pbs` with the token `state` and the role `DatastoreBackup` on
`/datastore/own-pbs/0docker` only (user and token); the token secret in `/etc/dockerhost-state-backup/token.secret` (0600), written straight from the PBS API into the file, never printed.
Recreate the token: delete it on own-pbs (`proxmox-backup-manager user delete-token backup-dockerhost@pbs state`), create it again with
`proxmox-backup-debug api create /access/users/backup-dockerhost@pbs/token/state`, add the ACL for `backup-dockerhost@pbs!state` and pipe the `value` into the file.

Commands: `dockerhost-state-backup check` (token reaches the namespace), `plan` (what a run would do, reads no data), `run` (`--skip-load-check` for a supervised run).
`zstd` is a prerequisite too (VM 100 has `/usr/bin/zstd` 1.5.5, Ubuntu's own package; `plan` says `zstd found` or `ZSTD MISSING`). Without it the run stages the copies uncompressed, all at once, and says so in a warning.

## Restore
Everything is read with the same repository and token (`export PBS_REPOSITORY='backup-dockerhost@pbs!state@10.10.10.1:8007:own-pbs' PBS_PASSWORD=$(cat /etc/dockerhost-state-backup/token.secret) PBS_FINGERPRINT=<fingerprint in config.json>`; the owner of the group can restore it).
```
proxmox-backup-client snapshot list host/dockerhost-state --ns 0docker
proxmox-backup-client restore host/dockerhost-state/<time> opt.pxar /restore/opt --ns 0docker          # one archive; add --allow-existing-dirs
proxmox-backup-client restore host/dockerhost-state/<time> staging.pxar /restore/staging --ns 0docker   # dumps, SQLite copies, inventory, MANIFEST.json
```
* Postgres: `gunzip -c /restore/staging/pg/<container>.sql.gz | docker exec -i <container> psql -U <POSTGRES_USER> postgres` (the dump drops and recreates what it holds).
* SQLite: stop the service, put the copy at `<original path>`, delete a leftover `-wal`/`-shm` next to it, start the service. A copy of 64 MiB or more is `/restore/staging/sqlite/<original path>.zst` (the
  original name plus `.zst`; smaller ones are plain files you just copy): `zstd -d -c /restore/staging/sqlite/<original path>.zst > <original path>` (needs the file's size free on the target; `zstd -d` checks the
  frame checksums itself), and compare with the `sha256` that `/restore/staging/MANIFEST.json` lists for that path: `zstd -d -c ....zst | sha256sum`. One file can be pulled alone:
  `proxmox-backup-client restore host/dockerhost-state/<time> staging.pxar /restore/one --ns 0docker --pattern '/sqlite/<original path>.zst'` (the client still reads the archive to its end, see below; check that
  the file exists afterwards: a pattern that matches nothing exits 0 and restores nothing).
* Whole host: new VM, the packages from `inventory/dpkg-selections.txt` (release in `inventory/os-release.txt`, Docker versions in `inventory/docker-version.txt`), restore `etc`, `opt`, `home`, `srv`, `root`, `volumes` and
  `usr_local`, recreate volumes that were not plain (`inventory/docker-volumes.json`) and the networks (`inventory/docker-networks-inspect.json`), `docker compose up -d` per project in `/opt` (`inventory/docker-compose-ls.txt`
  lists them), then the dumps and SQLite copies above. `tailscale` is the node's identity: restore it only when the old VM is gone, with tailscaled stopped. `dockernet` goes back with dockerd stopped. Do not restore
  `systemd_state/random-seed` onto a different machine.
* Restore drill (2026-10-22): see the end of this file. A `--pattern` restore reads the archive sequentially, so restoring one small volume costs about the time of reading the whole archive up to it and then the rest of it (the client does not stop early): restore from the front of the alphabet for a sample, and plan a full `volumes.pxar` restore (49 GiB, 13 GiB compressed) at 50 MiB/s through the relay on a quiet host and 30 MB/s or less on a starved one.

## Alerts
* `PbsBackupGroupStale` / `PbsBackupGroupStaleCritical` (26 h / 50 h) watch the group `0docker/host/dockerhost-state` like every other group.
* `DockerhostStateBackupFailed`: `dockerhost_state_backup_last_status == 0` for 30 minutes (the run failed, was skipped as busy, or finished with warnings such as a database that could not be dumped).
* `0docker/vm/100` is excluded from the daily stale alerts: its job is paused on purpose and the group is frozen.
* `dockerhost_state_backup_staging_peak_bytes` (the most the staging directory held during the last run) and `dockerhost_state_backup_staged_bytes` (what the client read) are exported; nothing alerts on them. Expected since 2026-10-29: peak about 10 GiB, staged about 4 GiB (they were 18 GiB both before).

## Limits and decisions
* **No client-side encryption** (`--crypt-mode none`). The old VM-level backups were not encrypted either, and a key needs a custody decision (a lost key loses every backup). The datastore is the fleet's own PBS.
  The snapshot holds `/root`, `/etc` and compose env files in clear, and since 2026-10-29 also the Tailscale node key and systemd's host key (see "Added on VM 100 on 2026-10-29"): that is one more reason to take the key
  decision. Say the word and a key goes into the vault.
* **Who can read the group `host/dockerhost-state` in namespace `0docker`** (own-pbs's `acl.cfg`, `user.cfg` and datastore, read on 2026-10-30 15:45Z; the group's owner is `backup-dockerhost@pbs!state`): the owner
  token itself (`DatastoreBackup` on `/datastore/own-pbs/0docker`: its own backups; the secret is root-only on VM 100, which holds all of this anyway); the read-only user `pbs-sync-0infer@pbs` and its token `pull`
  (`DatastoreReader` on the whole `/datastore/own-pbs`), which PBS #2 on VM 704 uses to copy the newest two snapshots, still in clear, into its own datastore (`pull-0docker`, daily 08:00Z,
  `docs/runbooks/tier0-infer-site.md`; PBS #2 itself was not looked at); and `root@pam`, so whoever is root on VM 620 (own-pbs) or on the 0own hypervisor that holds the datastore: it is an ext4 filesystem on a plain
  ZFS zvol, `encryption off` at both levels. `backup-writer@pbs` (tokens `vzdump-0docker`, `vzdump-0mcp`) and `pbs-sync@pbs` hold `DatastoreBackup` and `DatastoreAudit` on the whole datastore: they can list this
  group and write into the namespace, but read only the groups they own. No one else has a role on `/datastore/own-pbs/0docker`.
* **The repository is reached through the hypervisor** (`10.10.10.1:8007`, `config/0docker/dockerhost-pbs-relay`): the repository string in `config.json` points at the relay; the same string with `100.64.0.11` instead of `10.10.10.1:8007`
  is the fallback through VM 100's own tailnet (the grant stays). The next bullet is why.
* **Speed of the tailnet path.** VM 100 reaches own-pbs through a Tailscale DERP relay (`direct connection not established`, relay `nue`; the hypervisor itself has a direct path to own-pbs): measured 2026-10-21
  about 2.8 MB/s (22 Mbit/s, RTT 0.4 to 0.8 s under load) against 50 MiB/s for the old VM-level backups. A full first upload therefore takes hours: it was done in two runs (run 1 everything except the two
  Prometheus volumes, 35 GB and incompressible, run 2 with them; the second run only uploads what the first did not), and the tool's deadline is 6 h (the first attempt with 4 h would have been killed with most of it
  uploaded, and PBS does not resume an aborted backup: the chunks are sent again). After that a night uploads only the chunks that changed. Faster options if ever needed: a DNAT on the hypervisor
  (`10.10.10.1:8007` to `100.64.0.11:8007`, the grant of the hypervisor exists), or fixing the hole punching of VM 100's tailscaled.
* Daily load: the SQLite copies are about 17.5 GiB written to the guest's disk each night (chaos.db 8.5 GiB, graph.db 6.7 GiB, kuma.db 2.4 GiB, ...), plus about 3.8 GiB of compressed files since 2026-10-29 and the reads
  that compress and verify them. That is small next to the 5 MiB/s (430 GB/day) the guest already writes. What matters for the hypervisor is not this volume but how much of it exists at the same moment: see Staging peak.
* Switches (`config.json`): `limits.compress_min_bytes` 64 MiB (0 = stage every copy raw, all at once, as before 2026-10-29), `limits.compress_timeout_s` 3600, `limits.trim_wait_s` 300, `trim_staging` true (false = leave the freed blocks to the guest's hourly fstrim; refused unless `compress_min_bytes` is 0, see Staging peak).
  The level (`zstd -1`) is a constant in the script: on samples of the real files level 3 was 7 % smaller for twice the CPU. Rollback is one of these keys in the installed config, or the old script.
* Retention is PBS's own prune job `prune-0docker` (keep-last 3, daily 7, weekly 4). PBS#2 pulls the newest two snapshots with its `pull-0docker` job.
* Undo: `systemctl disable --now dockerhost-state-backup.timer`, delete `/etc/dockerhost-state-backup` and `/usr/local/sbin/dockerhost-state-backup`, `apt-get remove proxmox-backup-client qrencode`; on own-pbs delete the token and the user and optionally the group.

## Staging peak (2026-10-29)
**Why it matters.** VM 100's disk is a qcow2 file on the hypervisor's only filesystem (`/dev/md3`, 435.5 GiB; CI admission is held under 14 % free), and a block the guest writes stays allocated there until the guest
trims it (its `fstrim.timer` runs once an hour). The run used to stage every SQLite copy at once: 18.0 GiB for about 22 minutes on 2026-10-28 (12 minutes of staging, 10 of upload). The hypervisor's free space fell from
84.8 GB (18.1 %) at 17:31:30Z to 64.15 GB (13.72 %) at 17:55:30Z and was under the line from 17:47:30 to 17:56:00Z; it came back at 17:56:30 to 17:58:00Z through the hypervisor's reactive trim (it fires under 60 GiB), two
minutes after the staging was deleted at 17:54:10Z. Three files were 17.5 of the 18.0 GiB: chaos.db 8.47, graph.db 6.67, kuma.db 2.37 GiB.

**What the run does now** (details under "What one run does"): the copies are made one at a time, largest first; a copy of 64 MiB or more is compressed with `zstd -1`, read back and compared (sha256), and only then is the
raw copy deleted and its blocks trimmed (the directory is fsynced first: ext4 offers a freed block to FITRIM only once the delete has committed). The staging directory therefore holds one raw copy plus the compressed files so far,
and what is left of it is trimmed after the run too. What is backed up does not change: the same databases, the same single read snapshot per copy, the same snapshot, group and archives; only the files in `staging.pxar` are
`<name>.zst` for the big ones.

**Measured** on a quiet fleet VM (`0mcp_artifact_cache`, 4 vCPU): the real script, stand-ins for `docker` and the client (the client stand-in reads the staging directory and does the same zstd -1 and sha256 work), databases of
the production sizes (chaos.db 8.5, graph.db 6.7 with 84 % free pages, kuma.db 2.4 GiB, 5 mid-size and 40 small ones) generated to the compression ratios measured on the real files (zstd -1: kuma 4.06 against 4.08, graph 4.32 against 4.33,
chaos 5.58 against 5.56), a writer keeping all three open in WAL mode (about 130 MiB of un-checkpointed WAL each, 10 commits a second). The guest disk is modelled as a sparse file under an ext4 on a loop device, so the allocated size of
that file is what the hypervisor would see, and `fstrim` punches holes in it as on VM 100. The script ran in its own cgroup (memory.high 2.2 GiB, nice 19, idle I/O) with a CPU quota of one core and of 0.35 core (VM 100's service averaged
0.36 core on 2026-10-28: 7 min 57 s of CPU in 22 minutes).

| 1 run each, quiet host | old script | this change |
|---|---|---|
| peak staged on the guest | 18.18 GiB | 10.05 GiB |
| peak on the disk file (what the hypervisor sees) | 18.18 GiB | 10.05 GiB |
| staged when the client starts | 18.18 GiB | 4.07 GiB |
| seconds the disk file is more than 8 GiB above where it started (1 core / 0.35 core) | 436 / 539 | 189 / 408 |
| wall time (1 core / 0.35 core) | 387 / 501 s | 344 / 697 s |
| CPU seconds (1 core / 0.35 core) | 346 / 173 | 299 / 242 |
| written / read on the guest disk | 18.2 / 18.1 GiB | 22.1 / 24.7 GiB |

Run to run the wall time and the CPU of this VM move by 30 % (cold page cache: 19 GB of databases on 4 GiB of RAM), so read the last four rows as "the same order, up to 40 % more when the CPU is scarce": the run now compresses and verifies 17.5 GiB itself
instead of leaving the compression to the client (the client then reads 4.1 GiB: 33 s instead of 174 s on the bench). The two peaks are the figures that do not depend on timing.

**The trim is not optional.** The same change WITHOUT the trim (copies one at a time, compressed, raw deleted, nothing trimmed) peaked at 10.05 GiB on the guest but at **21.89 GiB on the disk file**, more than the old script: ext4 does
not reuse the blocks of a file it has just freed, so each copy lands on new blocks and the disk file grows by the sum of all copies and compressed files until the next trim. Hence the self-test (below), and the config rule that
`trim_staging: false` needs `limits.compress_min_bytes: 0`.

**Self-test.** Before the first copy the run writes 32 MiB in the staging directory, deletes it and trims it the way a copy is released; if FIEMAP gives no extents or FITRIM returns less than half of it, the run stages as before (all at once, uncompressed)
and ends failed with a warning that says so, rather than raise the hypervisor's peak. The first real run should show a `trimmed N MiB of freed staging blocks` line of about the raw size after each `compressed ...` line.

**Codec.** On samples of the real files, run on VM 100 itself at idle priority while its load was 41 to 46 (3 samples of 16 MiB of each of the three databases): zstd -1 4.57x at 117 MiB per CPU-second, zstd -3 4.91x at 58, zstd --fast=3 3.50x at 117, gzip -1 4.10x at 112 (gzip and pigz exist
on VM 100, lz4 does not). On the bench at a CPU quota of 10 %, 35 % and one core, 128 MiB of each database: zstd -1 10.4 / 65 / 145 MiB/s (7.2 CPU-seconds per GiB at one core), zstd -3 8.1 / 49 / 114, gzip -1 5.4 / 29 / 82 at a ratio 14 % lower.
Level 1 it is: the extra 7 % of size of level 3 costs about twice the CPU.

**What is left, and what would lower it further.** The peak is now the largest raw copy plus its compressed file (chaos.db: 8.5 + 1.5 GiB), the floor of this design. Deleting raw blocks while compressing (hole punching) would save the 1.5 GiB,
but a bug in it could destroy the only consistent copy, so it is not built. Staging in separate PBS groups, one per database, has the same floor and adds groups to alert on, prune, pull and restore, so it is not built either. A stream copy
(compress the pages as the backup API reads them) is not possible here: VM 100's libsqlite3 3.45.1 has no `sqlite_dbpage` and the backup API writes a seekable file. What would lower the floor are decisions for the owners, not made here: leaving chaos.db out
(a mirror of ProjectDiscovery's public Chaos corpus; its documentation does not call it disposable, and a rebuild loses `first_seen`/`last_seen` and the per-row `dataset_version` that its `/delta` consumers rely on; one line in `exclude.volumes`
does it), and graph.db, whose header says 86.5 % of its 1.75 million pages are free (a VACUUM by its owner would take about 5.8 GiB off the disk and the nightly copy). The timer slot is a separate decision (a drop-in on VM 100 moved it to 19:30Z on 2026-10-29;
the unit in this directory still says 17:30Z).

**After the first real run:** `journalctl -u dockerhost-state-backup` shows `compressed ...` and `trimmed ...` lines (six pairs: the three big copies and the three of 80 to 160 MiB), no WARNING; `dockerhost_state_backup_staging_peak_bytes` about 10.8e9 and
`dockerhost_state_backup_staged_bytes` about 4.4e9 (18.0 GiB for both before), `dockerhost_state_backup_warnings` 0; the run's own burst on the hypervisor is 2.3 points of the filesystem instead of 4.2, so that evening's low should sit about 1.9 points higher than the old run would have left it.

## First full run (2026-10-21 22:42Z, through the relay)
88.9 GiB logical in 7 archives, **35 GiB uploaded** (zstd; /home and the Prometheus blocks compress badly), 2985 s of upload at 49 to 57 MiB/s for the big archives, plus 17 min of staging when the host is quiet and
about 1 h 20 min when it is not (VM 100 sat at load 40 to 70 with CPU pressure 63 %: the idle-priority copies are starved, which is why the limits are generous). Per archive, logical to uploaded: etc 22 MB to 1.2 MB, opt 8.7 to 3.9 GiB,
home 16.9 to 13.5 GiB, srv 4.5 to 1.6 GiB, root 1.9 to 1.2 GiB, volumes 49.0 to 13.3 GiB (Prometheus 34.6 GB of it), staging 7.9 to 1.8 GiB. The first attempt over the DERP relay (2.7 MB/s) was stopped after 10.9 GB sent.
Warnings of that run: one, chaos.db's online copy timed out (see the check split above); it was in the snapshot as a raw copy of a live WAL database, so the next night replaced it with a staged copy.

## Restore drill (2026-10-22, from snapshot 2026-10-21T22:42:42Z and 2026-10-22T05:36:20Z, through the relay, on the live host)
* `etc.pxar` restored whole (1332 files, 28 MB): identical to the live `/etc` (`diff -r`, apart from the tool's own directory).
* `staging.pxar`, selected parts (`--pattern /pg ...`): 12 Postgres dumps, all pass `gunzip -t`; 4 SQLite copies. 685 s for the restore on a CPU-starved host (load 57).
* Postgres: `0init-readeck-db` (postgres:17) and `app_wemeshup_com-db-1` (postgres:16) restored into scratch containers of the same image (`--network none --cpus 1 --memory 512m`): same databases, 8 of 8 and 277 of 277 tables,
  row counts of the five biggest tables equal (the live `job_queue` had moved on by 987 rows in the hours since the dump, as expected).
* SQLite copies (`keys.db`, `grafana.db`, dns-sync `state.db`, `secrets.db`): `PRAGMA integrity_check` ok on all four, per-table counts equal to the live ones except tables that kept growing (audit logs).
* Files: `volumes.pxar` pattern `/0init-readeck-data`: 1489 files, 480 MB, all 1489 byte-identical (sha256) to the live ones. The restore took the 1500 s limit of the drill because the client reads the archive to its end.
* Not drilled that day: restoring the large staged SQLite copies (graph.db, chaos.db, kuma.db: their copy is a single read snapshot and they are above the check cap) and a whole-host rebuild. The compressed large copy was drilled on 2026-10-29 on a scratch PBS (next section); a restore from own-pbs itself and a whole-host rebuild still are not.

## Restore drill of a compressed large copy (2026-10-29, scratch PBS)
Run on the quiet fleet VM against a throwaway Proxmox Backup Server (PBS 3.4.9, in a container, nothing shared with own-pbs or VM 100) with the real `proxmox-backup-client` 3.4.9 (the VM 100 build: the same package sha256 as in Install),
the real script and databases of the production sizes (synthetic content, chaos.db 8.5 GiB with 45 million rows, graph.db 6.7 GiB, kuma.db 2.4 GiB). The script made one snapshot (`staging.pxar` 4.07 GiB, the snapshot 4.37 GB on the PBS), and
the recipe of the Restore section was followed for chaos.db:
* `proxmox-backup-client restore host/dockerhost-state/<time> staging.pxar /restore --ns 0docker --pattern '/sqlite/<original path>.zst'` (and the same for `/MANIFEST.json`, with `--allow-existing-dirs`): 32 s for the 1.64 GB file on a local PBS;
  the file's size equals `staged_bytes` in the manifest.
* `zstd -d -c ....zst > chaos.db`: 11 s, 9,150,820,352 bytes (`copy_bytes`), and its sha256 equals the manifest's (**equal**). SQLite opens it (`journal_mode` delete, 2,234,087 pages, no freelist), `PRAGMA quick_check` says `ok` (572 s on 2 CPUs),
  and the counts equal those of the source database (45,000,000 rows of `subdomains` with the same smallest and largest rowid, 5,000 `programs`, a checksum over every 997th row).
* A second run with the final version of the script, with the staging on an ext4 directory so that the self-test and the trims are real (`trimmed 9006 MiB` right after the chaos.db copy was compressed, no warning,
  `dockerhost_state_backup_staging_peak_bytes` 10,791,449,515), gave the same compressed size and sha256, the same snapshot size and the same counts; its `quick_check` was not repeated.
Through the relay from VM 100 to own-pbs the same restore is slower: plan on the figures in the Restore section (about 30 to 50 MiB/s, and a pattern restore still reads the archive to its end).
