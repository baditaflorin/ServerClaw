# fleet_pg_backup

The Postgres backup stack that spans three hosts of two fleets, declared in one place:

| Component | Host | What it manages |
|---|---|---|
| `pve_backup` | 0database hypervisor (pve01) | the vzdump metrics hook, the PBS storage entry (non-secret fields), the `pg-primary-daily-pbs` job |
| `pgbackrest` | pg-primary | `/etc/pgbackrest` layout and `pgbackrest.conf`, the daily wrapper, the prepared (not installed) service and timer |
| `pbs_server` | own-pbs | the realm user, its ACLs, the per-namespace prune job; verifies the namespace and the API token exist |

Secrets are references only. The PBS token secret file (`/etc/pve/priv/storage/<id>.pw`) and the pgBackRest
passphrase file (`conf.d/10-repo-cipher.conf`) are checked for existence, ownership and mode and are never read,
created or logged. `archive_mode` and `archive_command` are never touched.

The vzdump hook fixes the "size and duration read 0 after a successful run" bug: vzdump exports `LOGFILE` only for
directory targets, so a PBS target never reached the log parser. The hook now falls back to
`/var/log/vzdump/<vmtype>-<vmid>.log` and takes the vmid from its third argument.
