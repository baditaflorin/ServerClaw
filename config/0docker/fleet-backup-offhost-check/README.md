# fleet-backup-offhost-check: is the off-host copy of the small encrypted backup archives really there?

Installed on the 0docker Docker host VM (VM 100, `ubuntuvm1`, tailnet 100.64.0.7). The VM is not managed by Ansible or fleet-runner, so this directory is the source of truth:
change a file here through a PR, then install it as below. Runbook (what to do when an alert fires): `docs/runbooks/fleet-backup-offhost-copy.md`.

## Why this exists
The sidecar `fleet-backup-sync` (go-fleet-backup, `ops/fleet-backup-sync`) copies the newest age-encrypted archive of `secrets-db`, `keystore-db` and `broker-db-snapshot` from the
NFS backup target to the private GitHub repository `fleet-backups` (`payload/<source>.age`, or `payload/<source>.age.part-000`, `-001`, ... above 45 MiB, plus `payload/state.tsv`).
It is the only copy outside the providers of both hypervisors. Nothing watched it. On 2026-10-22 the keystore-db archive had grown from 43 MB to 91 MB in six days and was about to
pass the sidecar's 90 MiB cap and GitHub's 100 MB file limit; the copy would have gone stale without a single alert, and the only thing that would have noticed (the daily health report) runs on the
operator's Mac, which had slept for three days.

## What it does
| mode | timer | what it reads | what it publishes (node_exporter textfile) |
|---|---|---|---|
| `check` | every 30 min (`:12`, `:42`) | a partial clone of the branch head WITHOUT file contents, the tree listing by name, and the one small `payload/state.tsv` | `fleet_backup_offhost.prom`: when each source was last copied, the archive's own time, parts, size, and `present` (every file of the copy is in the tree, nothing stray) |
| `deep` | daily 12:20Z | everything (about 160 MB today): rebuilds each archive from its parts | `fleet_backup_offhost_deep.prom`: per source `ok` (SHA-256 of the rebuilt archive equals `state.tsv`, it starts with the age header, its size equals `state.tsv`), bytes, last success |

It only READS the repository, with the sidecar's own deploy key and pinned `known_hosts` (read from `/opt/services/fleet-backup-sync/`, root on the same host). It cannot decrypt anything.
Exit codes: 0 ok, 1 the repository could not be read, 2 the copy is damaged or incomplete. A failed run keeps the previous per-source values (timestamps are absolute, so `time() - x` keeps
growing) and does not move the last-success time. Alerts: `config/prometheus/rules/fleet-backup-offhost.yml` (CopyStale 36 h, CopyVeryStale 72 h, CopyBroken, CheckStale, DeepCheckFailed,
DeepCheckStale).

## Install / undo (as root on VM 100; every step keeps a backup of what it replaces)
```bash
tar -C config/0docker/fleet-backup-offhost-check -cf - . | ssh dockerhost 'd=$(mktemp -d) && tar -C $d -xf - && sudo bash $d/install.sh; rm -rf $d'
tar -C config/0docker/fleet-backup-offhost-check -cf - . | ssh dockerhost 'd=$(mktemp -d) && tar -C $d -xf - && sudo bash $d/install.sh --undo; rm -rf $d'
```
`install.sh` validates (python syntax, JSON, git, the sidecar's key files), installs `/usr/local/sbin/fleet-backup-offhost-check`, `/etc/fleet-backup-offhost-check/config.json` and four units,
runs ONE real `check` before enabling the timers and undoes itself when the repository cannot be read (exit 1). Then deploy the rules file to the monitoring Prometheus (backup, `promtool check`, HUP).
Manual runs: `sudo fleet-backup-offhost-check check --dry-run` (prints the metrics, writes nothing) and `... deep`.

## Config (`/etc/fleet-backup-offhost-check/config.json`)
`repo`, `branch`, `deploy_key`, `known_hosts` (the sidecar's files), `sources` (plain names), `textfile` and `deep_textfile`, `tmpdir` (`/var/tmp`, the deep check needs room for the payload), `fetch_timeout_s`.
No secret is in the file. Add a source to `sources` when `BACKUP_SYNC_PAYLOAD_SOURCES` gets one.

## Tests
`tests/test_fleet_backup_offhost_check.py` runs the tool against real local git repositories with partial clone enabled (a missing part, a stray file, an unreadable repository, one flipped
byte in one part, content that is not an age file, a size mismatch, legacy four-column lines, and that the 30-minute check reads nothing but `state.tsv`);
`tests/test_fleet_backup_offhost_rules.py` plus `tests/promtool/fleet_backup_offhost_rules_test.yml` pin the alerts. Mutation checks on 2026-10-22: 16 of 16 mutants of the tool and 15 of 15
of the rules killed.
