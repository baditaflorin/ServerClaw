# Tier-0 replication (vault + keystore)

CT108 runs `tier0-snapshot.timer` every 5 minutes (`scripts/tier0/tier0-snapshot.sh` in fleet-state): online SQLite backup of the Go
Fleet Secrets and keystore databases on VM100, gzip, **encrypted to the operator's recipient certificate before leaving the 0docker
site**, pushed to two other sites (0mcp docker-build, 0own build worker) and checksum-verified there. The private key is not on any
server. Alerts: `Tier0SnapshotStale` (critical), `Tier0ReplicaMissing`, `Tier0SnapshotMetricsAbsent` (`config/prometheus/rules/tier0.yml`).

Restore drill (run from a machine holding the private key): `tier0-restore-test.sh 0mcp_docker_build:sudo latest` and `... 0own_build_worker latest`.
It decrypts, checks sha256 + SQLite integrity + row counts against the manifest. Run it monthly and after any change to the job.
When the 0docker site is down the stale alert is expected; replicas keep the last verified snapshot (2 h dense, hourly 2 days, daily 30 days).

## CI standby (ci.0exec.com Woodpecker server, runs inside CT108)
`tier0-ci-snapshot.timer` (hourly) takes a slim online backup of `woodpecker.sqlite` (log_entries dropped: ~1.4 GB becomes ~100 MB), plus
`/opt/woodpecker/.env` and the compose files, encrypts both to the recipient cert and verifies them on the same two replica sites
(`/var/lib/tier0-replica-ci`). Alerts: `Tier0CISnapshotStale`, `Tier0CIReplicaMissing`.
Drill (from a machine with the private key): `scripts/tier0/tier0-ci-drill.sh 0own_build_worker latest` restores into a tmpfs, boots the same
server image on localhost, checks `/healthz`, that the admin token authenticates against the restored DB and that a known repo is present, then
destroys everything. Last run: healthy, `login=baditaflorin admin=True`, repo id 4 active, 0 fatal log lines.
Failover outline (fleet-state docs/tier0-multihost-design.md 4.3): restore the files on the standby host, `docker compose up -d woodpecker-server`
with the restored `.env`, then move `ci.0exec.com` (edge upstream or DNS) to it and re-point remote agents' `WOODPECKER_SERVER` (the 0mcp agent uses
`10.10.10.20:9000`). All 429 repo webhooks keep working because the server identity and database are the same. Pipeline logs are not replicated.

## Key escrow (vault master key)

`tier0-key-escrow.sh` (CT108, daily 03:45 UTC, `tier0-key-escrow.timer`) reads the master key, both admin tokens and the full environment of
`go-fleet-secrets` and `go-apikey-service` on VM100, encrypts the bundle in memory to the Tier-0 recipient certificate and stores the ciphertext
under `<replica>/escrow/<ts>/` on both replica sites (last 10 kept, `escrow/latest` symlink). No server can open it; the operator's offline
private key is required. Alerts: `Tier0EscrowStale`, `Tier0EscrowReplicaMissing`, `Tier0EscrowMetricsAbsent`.

Prove it end to end from the machine holding the private key (boots the real vault + keystore from the replica using ONLY the escrowed key and
compares a real secret with the live vault): `TIER0_DRILL_ESCROW=1 scripts/tier0/tier0-vault-drill.sh <replica-host[:sudo]>` (fleet-state repo).
By hand: `openssl smime -decrypt -binary -inform DER -inkey tier0-backup.key -in escrow/latest/vault-config.json.p7`.
