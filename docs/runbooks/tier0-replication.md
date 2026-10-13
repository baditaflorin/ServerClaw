# Tier-0 replication (vault + keystore)

CT108 runs `tier0-snapshot.timer` every 5 minutes (`scripts/tier0/tier0-snapshot.sh` in fleet-state): online SQLite backup of the Go
Fleet Secrets and keystore databases on VM100, gzip, **encrypted to the operator's recipient certificate before leaving the 0docker
site**, pushed to two other sites (0mcp docker-build, 0own build worker) and checksum-verified there. The private key is not on any
server. Alerts: `Tier0SnapshotStale` (critical), `Tier0ReplicaMissing`, `Tier0SnapshotMetricsAbsent` (`config/prometheus/rules/tier0.yml`).

Restore drill (run from a machine holding the private key): `tier0-restore-test.sh 0mcp_docker_build:sudo latest` and `... 0own_build_worker latest`.
It decrypts, checks sha256 + SQLite integrity + row counts against the manifest. Run it monthly and after any change to the job.
When the 0docker site is down the stale alert is expected; replicas keep the last verified snapshot (2 h dense, hourly 2 days, daily 30 days).
