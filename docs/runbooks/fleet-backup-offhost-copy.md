# Off-host copy of the small encrypted backup archives (GitHub)

What it is: the sidecar `fleet-backup-sync` on the Docker host VM (VM 100, `/opt/services/fleet-backup-sync`) copies the newest age-encrypted archive of `secrets-db`,
`keystore-db` and `broker-db-snapshot` from the NFS backup target to the private repository `baditaflorin/fleet-backups`, at most once a day:
`payload/<source>.age`, or `payload/<source>.age.part-000`, `-001`, ... for an archive above 45 MiB, and `payload/state.tsv` (one line per source: name, SHA-256 of the whole
archive, copy time, number of parts, size in bytes). It is the only copy outside the providers of both hypervisors. The archives are encrypted to the offline age key; nothing else
decrypts them.

What watches it (since 2026-10-22): `config/0docker/fleet-backup-offhost-check` on VM 100. `fleet-backup-offhost-check.timer` (every 30 minutes) reads the repository head and
`state.tsv` without downloading the payload; `fleet-backup-offhost-deep.timer` (12:20Z) downloads everything and rebuilds each archive from its parts. Alerts
(`config/prometheus/rules/fleet-backup-offhost.yml`): CopyStale (36 h), CopyVeryStale (72 h), CopyBroken (a file missing or stray), CheckStale (the checker itself), DeepCheckFailed
(sha256, age header or size does not match), DeepCheckStale (no good deep check for 50 h).

## When CopyStale / CopyVeryStale fires
1. `ssh dockerhost 'docker logs --since 26h fleet-backup-sync 2>&1 | grep -v "inventory unchanged" | tail -20'`. The causes seen so far:
   * `not copied` with a size: the archive is above `BACKUP_SYNC_PAYLOAD_MAX_BYTES` (compose default 300 MiB; the host's `runtime.env` may carry its own value).
   * `tmp too small`: the sidecar's tmpfs (`BACKUP_SYNC_TMP_SIZE`, 1024m since 2026-10-22) must be at least four times the combined payload, and the container's `mem_limit` with it.
   * `cannot inspect remote branch`: GitHub or the deploy key; one such line a day is normal noise, a stream of them is not (the REST rate limit does not apply to git over SSH).
2. `ssh dockerhost 'docker inspect fleet-backup-sync --format "{{.State.Status}} restarts={{.RestartCount}}"'`.
3. A source that is listed in `BACKUP_SYNC_PAYLOAD_SOURCES` but whose NFS directory is empty is skipped with `no archive`: check the backup service first (`docker logs go-fleet-backup`).

## When DeepCheckFailed fires
Do not trust the copy. Read `journalctl -u fleet-backup-offhost-deep -n 30` on VM 100: it names the source and what differs. A SHA-256 mismatch with all parts present means a part
was replaced or truncated (or a push of a new archive is half done; run `systemctl start fleet-backup-offhost-deep.service` again after the next sidecar cycle). The archive on the
NFS target (`/var/lib/docker/volumes/fleet-backup_backup-destination/_data/<source>/`) and the file-level state backup on PBS are the other copies.

## Restore from the off-host copy
`git clone git@github.com:baditaflorin/fleet-backups.git`; for a split archive `cat payload/<source>.age.part-* > <source>.age` (the names sort in order); compare
`sha256sum <source>.age` with the line in `payload/state.tsv`; decrypt with the offline age key.

## Undo
`tar -C config/0docker/fleet-backup-offhost-check -cf - . | ssh dockerhost 'd=$(mktemp -d) && tar -C $d -xf - && sudo bash $d/install.sh --undo; rm -rf $d'` removes the units, the
tool, the config and both textfiles; delete `/etc/prometheus/rules/fleet-backup-offhost.yml` on the monitoring VM and send Prometheus a HUP to drop the alerts.
