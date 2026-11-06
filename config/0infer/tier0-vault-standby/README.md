# Tier-0 vault/keystore warm standby (VM704 `infer-tier0`)

These are the files of the vault + keystore warm standby on `infer-tier0` (0infer Proxmox host, VM704). The host is not managed by
Ansible or fleet-runner, so this directory is the source of truth: change a file here through a PR, then install it as below.
They were copied byte-identical from the live host on 2026-10-17. What the standby is, the courier, the alerts and the image pins:
`docs/runbooks/tier0-infer-site.md`.

| File here | Live path | Owner, mode |
|---|---|---|
| `compose.yml` | `/opt/tier0/vault-standby/compose.yml` | debian:debian 0664 |
| `drill.sh` | `/opt/tier0/vault-standby/drill.sh` | debian:debian 0755 |
| `drill_check.py` | `/opt/tier0/vault-standby/drill_check.py` | root:root 0700 (it opens the root-only `.env`) |
| `promote.sh` | `/opt/tier0/vault-standby/promote.sh` | debian:debian 0775 |
| `vault-standby-receive` | `/usr/local/bin/vault-standby-receive` | root:root 0755 |
| `vault-standby-drill.service`, `vault-standby-drill.timer` | `/etc/systemd/system/` | root:root 0644 |

Not in git, on purpose:
- `/opt/tier0/vault-standby/.env` (root 0600) holds the secrets. Never copy, print or commit it. Variables: `SECRETS_MASTER_KEY`,
  `SECRETS_ADMIN_TOKEN`, `KEYSTORE_ADMIN_TOKEN`, `VSYNC_UID`, `VSYNC_GID`, and the optional `SECRETS_MASTER_KEYS`, `SECRETS_ACTIVE_KEY_ID`,
  `SECRETS_WRITE_V2`, `SECRETS_REQUIRE_ROW_MAC`. `drill_check.py` reads `KEYSTORE_ADMIN_TOKEN` and `SECRETS_ADMIN_TOKEN` from it at run time
  and prints only `records=N`.
- `data/` (the courier's SQLite copies, owner `vsync`, 0700 per service) and the `compose.yml.bak-*` backups.
- On CT108: `/root/.ssh/tier0_sync` (the courier's PRIVATE key, root 0600) and `/root/.ssh/known_hosts_tier0` (host-key pin). See the courier section.

## Install or update a file
1. Guard first. A running standby is a real promotion: change nothing while it runs.
   `cd /opt/tier0/vault-standby && sudo docker-compose ps --status running` must print no container.
2. Copy the file to the host (for example `scp drill.sh 0infer_tier0:/tmp/`), then back up the live copy with the date:
   `sudo cp -p /opt/tier0/vault-standby/drill.sh /opt/tier0/vault-standby/drill.sh.bak-$(date -u +%Y%m%d)`.
3. Install it with the owner and mode from the table:
   `sudo install -o debian -g debian -m 0755 /tmp/drill.sh /opt/tier0/vault-standby/drill.sh`.
   `sha256sum` on the host must equal `shasum -a 256` of the file here.
4. Units: after installing them, `sudo systemctl daemon-reload && sudo systemctl enable --now vault-standby-drill.timer`.
5. Test with one drill: `sudo systemctl start vault-standby-drill.service`, then
   `journalctl -u vault-standby-drill.service -n 3` must say `PASS` and
   `/var/lib/prometheus/node-exporter/vault_standby_drill.prom` must contain `vault_standby_drill_last_success 1`.
   `compose.yml` changes (image pins) use the same test, see the runbook.

Rollback: install the `.bak-<date>` copy the same way and run the drill again.

## Courier on the Builder (CT108): `ct108-courier/`
The other half of the standby. It runs on the Builder, not on VM704, and was copied byte-identical from CT108 on 2026-10-17.

| File here | Live path (on CT108) | Owner, mode |
|---|---|---|
| `ct108-courier/vault-standby-send` | `/usr/local/sbin/vault-standby-send` | root:root 0755 |
| `ct108-courier/vault-standby-send.service`, `.timer` | `/etc/systemd/system/` | root:root 0644 |

Every 2 minutes (`OnUnitActiveSec=120s`, run under `flock -n`) it takes a WAL-safe `sqlite3 .backup` of the vault and keystore databases on the dockerhost
(over ssh as `ubuntu_vm` with sudo, retried 4 times), gzips them and streams each to `vsync@<0infer host>:2240`, which is forwarded to VM704's `vault-standby-receive`.
It writes the textfile metric `vault_standby_sync_*` (alerts `VaultStandbySyncStale|VeryStale|Missing`) and exits 1 if any push failed; a failed run still publishes
`vault_standby_sync_last_success 0`.

Needs on CT108, none of it in git: `/root/.ssh/tier0_sync` (private key; the public half is the single forced-command line in VM704's `vsync` authorized_keys),
`/root/.ssh/known_hosts_tier0` (pins the host key of `[<0infer host>]:2240`, checked with `StrictHostKeyChecking=yes`), key-only ssh from CT108 to the dockerhost,
tailscaled in userspace mode with its CONNECT proxy on `127.0.0.1:1056` (the script reaches the tailnet through `nc -X connect`), `nc`, and the node_exporter textfile
directory `/var/lib/prometheus-node-exporter/textfile` (without it the script skips the metric).

Install or update (the same backup, install, test and rollback steps as above, on CT108): back up with `sudo cp -p <file> <file>.bak-$(date -u +%Y%m%d)`, install with
`sudo install -o root -g root -m 0755` (script) or `-m 0644` (units), `sudo systemctl daemon-reload`, `sudo systemctl enable --now vault-standby-send.timer`.
Test with `sudo systemctl start vault-standby-send.service` (a manual start while a run holds the lock exits silently), then `journalctl -u vault-standby-send.service -n 5`
must show `ok secrets.db ...` and `ok keys.db ...` from the receiver, `/var/lib/prometheus-node-exporter/textfile/vault_standby_sync.prom` must say `vault_standby_sync_last_success 1`,
and `data/{vault,keystore}/.last_sync` on VM704 must be seconds old.

**While the standby runs** (the weekly drill, `tier0-secret` reading a secret for the runner's DNS stage and its daily rehearsal, or a manual `promote.sh`): `vault-standby-receive` refuses every upload while anything listens on the standby's published
ports (`127.0.0.1:18021` keystore, `127.0.0.1:18140` vault; docker-proxy binds them as soon as a container starts, and the receiver, which runs as `vsync` without docker access,
probes them with a connect). A refusal exits 5 with `refused: the standby is running (promoted?), not replacing its data`, writes nothing, creates no `.incoming` or history
file, and first reads and discards the upload: leaving it unread would SIGPIPE the courier's snapshot step on the dockerhost, which then skips its cleanup and leaves a root-only
copy of the database in its `/tmp`. The courier sees `push ... FAILED` and publishes `vault_standby_sync_last_success 0` for those runs; the sync alerts are timestamp based
(stale after 15 minutes), so a drill or a rehearsal does not page, a long run does, which is correct because the copy is then not being refreshed. The check runs twice:
before the upload is accepted and again right before the swap, so a standby that starts mid-upload is still refused. The ports it watches must match the `ports:` of `compose.yml`
(a test compares them).

**Which promotion writes here.** The automated failover (`tier0-failover.sh --promote`, run by the runner's controller and executor) promotes the vault on the 0mcp standby host from
the encrypted replicas, with its data in `/var/lib/tier0-promoted` there and `PROMOTED.json` next to it. It never writes this directory, so the courier keeps feeding this copy
from whatever primary answers, and the refusals above protect the short windows in which the standby runs here: a push must not swap the database, or delete `-wal`/`-shm`, under it.
Only a manual `promote.sh` on VM704 turns this copy into a writer. After such a manual promotion the guard holds only while the containers run: the first push after they are
stopped replaces the databases with the dockerhost's, so before stopping a manually promoted standby copy what it wrote back to the primary, or stop `vault-standby-send.timer` on
CT108 until that is decided. A persistent "promoted" fence for this directory was considered and not built: nothing in the automated path writes here, so nothing would set it.

## Rebuild on a fresh host
- Packages: `docker.io`, `docker-compose` (the drill uses the `docker-compose` command, 2.26 on Debian), `sqlite3`, `python3`, `curl`,
  `util-linux` (flock), `prometheus-node-exporter` with the textfile directory `/var/lib/prometheus/node-exporter`.
- User `vsync` (its numeric uid and gid go into `.env` as `VSYNC_UID` and `VSYNC_GID`; the containers run as that user).
  `mkdir -p /opt/tier0/vault-standby/data/{vault,keystore}` and `chown -R vsync:vsync /opt/tier0/vault-standby/data`.
- Courier key: one line in `/home/vsync/.ssh/authorized_keys`,
  `command="/usr/local/bin/vault-standby-receive",restrict ssh-ed25519 <public key of /root/.ssh/tier0_sync on CT108>`.
  The receiver only accepts `put secrets` and `put keystore` and logs to `/home/vsync/receive.log`.
- Images: `docker save` the pinned tags on the dockerhost and `sudo docker load` them here (the runbook has the steps).
- Write `.env` (root 0600) from the primary's values, install every file from the table, enable the timer and run one drill.

## Tests
`tests/test_tier0_vault_standby_drill.py` runs `drill.sh` against stub `docker-compose`, `curl`, `sleep` and `flock` commands: pass, the
real-promotion guard, stale copies, a record-count drop, containers that exit only after `stop` has returned, and containers that never
stop. `tests/test_tier0_vault_standby_courier.py` does the same for `ct108-courier/vault-standby-send` with a stub `ssh`: both pushes in order with the pinned
options, a failed push or snapshot (exit 1, metric `last_success 0` still published), and a missing textfile directory.
`tests/test_tier0_vault_standby_receiver.py` runs `vault-standby-receive` itself (stub `sqlite3`, real loopback listeners standing in for the standby): a normal swap, a refusal on either
port with the upload drained and nothing touched, a standby that starts mid-upload, still-denied commands, and the watched ports equal to the compose ports.
