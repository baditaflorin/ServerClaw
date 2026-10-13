# Backup Restore Verification

## Production safety gate

Do not assume the configured fixture bridge is isolated because this runbook
calls it a staging bridge. The runner requires an explicit isolated fixture,
no default gateway, no overlap with managed guest addresses, and a Proxmox
bridge with no host IPv4 address or attached ports. Verify restore storage and
available host capacity before booting any restored guest. If isolation or
capacity cannot be proven, stop before starting the restored VM and record the
blocker; do not improvise a subnet or reuse the source guest's network identity.

The generic workflow must also use the storage identifier and restore target
appropriate to the deployment. Its historical defaults may not match an
already-running private environment. Confirm both values with read-only
Proxmox queries before invoking `make restore-verification`.

ADR 0099 adds a repository-managed restore verification workflow that restores the highest-risk PBS-protected guests into a configured, verified isolated bridge, runs smoke tests, writes a receipt, and tears down only VMs created by the current run.

ADR 0190 extends the `docker-runtime` portion of that flow with a privacy-safe synthetic transaction replay so recovery validation records request success rate and latency distribution instead of only single-shot smoke checks.

ADR 0272 extends the same workflow with restore-readiness ladders and governed warm-up profiles so receipts record the highest completed recovery stage instead of only a binary final result.

## Entry Points

- local run: `make restore-verification`
- direct script: `uv run --with pyyaml python scripts/restore_verification.py`
- standalone replay: `python3 scripts/synthetic_transaction_replay.py --target restore-docker-runtime --dry-run`
- Windmill worker wrapper: `python3 config/windmill/scripts/restore-verification.py`
- receipts: `receipts/restore-verifications/*.json`
- optional ADR 0187 seed staging: `python3 scripts/restore_verification.py --seed-class standard`

For focused recovery drills or ADR-local replays, scope the run to one or more guests:

- `make restore-verification RESTORE_ARGS='--targets docker-runtime --storage-id lv3-backup-pbs --restore-storage local --selection-strategy latest --ssh-timeout-seconds 900'`
- Override `--storage-id` and `--restore-storage` with values confirmed on the selected Proxmox host; do not assume the generic defaults match a private deployment.

## Targets

The current repository defines restore targets for three guests:

- `postgres` restored to VMID `900`
- `docker-runtime` restored to VMID `901`
- `backup` restored to VMID `902`

The fixture network values are configuration only. The current fixtures are
marked `isolated: false` until a dedicated isolated bridge and non-overlapping
addresses are provisioned and verified; therefore they are not eligible for a
live restore today.

## Workflow

1. Query `sudo pvesm list <storage-id>` on the Proxmox host, using the same `--storage-id` supplied to the workflow.
2. Require an explicit isolated-network fixture with no gateway, no address overlap with managed guests, an unaddressed/empty Proxmox bridge, and an approved capacity result.
3. Refuse the restore if the target VMID already exists anywhere in the Proxmox cluster; existing VMs are never removed to make room. A VMID becomes run-owned only after `qmrestore` succeeds.
4. Select one backup per target from the last 7 days and restore it to the selected `--restore-storage`.
5. Rewire the restored guest to the verified isolated bridge without a default gateway, keep the generated unique MAC, refresh cloud-init, and boot it.
6. Use QEMU guest-agent access for isolated guests; do not rely on SSH from the Proxmox host into a network intentionally lacking a host-side address.
7. Optionally stage an ADR 0187 seed snapshot under `/var/lib/lv3-seed-data/restore-verification/<vm-name>/` only when the fixture explicitly enables the SSH path.
8. Apply the declared restore-readiness profile from `config/restore-readiness-profiles.json`.
9. Record the readiness ladder stages:
   - restore completed
   - guest boot completed
   - guest access path ready
   - network and dependency path ready
   - service-specific warm-up completed
   - synthetic replay window passed
10. Run repeated guest-local warm-up checks until the profile passes or its attempt budget is exhausted. Confirm host-published service bind addresses work on the fixture before treating app readiness as meaningful.
11. Replay the ADR 0190 synthetic control-plane transactions only when the profile declares synthetic replay and the service-specific warm-up stage has already passed.
12. Write one JSON receipt under `receipts/restore-verifications/`.
13. Emit the mutation-audit event and optional NATS plus Mattermost notifications.
14. Mark the restored guest with a unique per-run Proxmox tag, then verify that exact tag before cleanup. Destroy only a matching run-owned VMID; pre-existing, replaced, unmarked, or unverifiable VMs are left untouched and cleanup failure is written into the verification result.

Isolated fixtures use QEMU guest-agent (`qga`) for guest-local smoke commands and synthetic replay. Non-isolated legacy fixtures may use SSH with a QGA fallback, but the runner will refuse their live execution until they meet the isolation checks.

## Restore-Readiness Profiles

The canonical restore-readiness catalog lives at `config/restore-readiness-profiles.json` and is validated against `docs/schema/restore-readiness-profiles.schema.json`.

Current profiles:

- `postgres`: waits briefly for PostgreSQL to settle, treats `postgres_ready` as the network and dependency gate, then requires the schema and dump checks to pass before the warm-up stage is complete.
- `backup-vm`: waits briefly for PBS to settle, treats `backup_pbs_port` as the network gate, then requires `proxmox-backup-manager datastore list` to pass before the warm-up stage is complete.
- `docker-runtime`: waits for the restored runtime to settle, retries Authentik, NetBox, and Windmill local readiness until they all pass or the profile budget is exhausted, then replays the governed `restore-docker-runtime` synthetic transaction window.

Each receipt now records:

- `readiness_profile`
- `readiness_ladder`
- `warm_up_attempts`
- `summary.highest_completed_stage_counts`

That evidence makes it clear whether a restore failed before guest access, during service warm-up, or only after the replay window began.

## Smoke Tests

### postgres

- `pg_isready` on localhost
- one `psql` table-count query per managed database
- one `pg_dump --schema-only` per managed database

### docker-runtime

- Authentik readiness endpoint from the local guest
- NetBox readiness endpoint from the local guest
- Windmill readiness endpoint from the local guest
- OpenBao readiness endpoint as a non-blocking observation
- repeated synthetic control-plane reads for Authentik readiness, NetBox login, Windmill API version, and OpenBao health with per-request latency capture

### backup

- TCP reachability on `127.0.0.1:8007`
- `proxmox-backup-manager datastore list --output-format json`

## Optional Outputs

If these variables are present when the workflow runs, the script also writes summary metrics for the managed Grafana platform overview dashboard:

- `RESTORE_VERIFICATION_INFLUXDB_URL`
- `RESTORE_VERIFICATION_INFLUXDB_BUCKET`
- `RESTORE_VERIFICATION_INFLUXDB_ORG`
- `RESTORE_VERIFICATION_INFLUXDB_TOKEN`

If this variable is present, the workflow posts the summary to Mattermost:

- `RESTORE_VERIFICATION_MATTERMOST_WEBHOOK`

If `--publish-nats` is set, the workflow emits:

- `platform.backup.restore-verification.completed`
- `platform.backup.restore-verification.failed` when any target fails

## Verification

- `python3 -m py_compile scripts/restore_verification.py scripts/synthetic_transaction_replay.py scripts/smoke_tests/postgres_smoke.py scripts/smoke_tests/docker_runtime_smoke.py scripts/smoke_tests/backup_vm_smoke.py config/windmill/scripts/restore-verification.py`
- `uv run --with pytest --with pyyaml pytest tests/test_restore_verification.py tests/test_restore_verification_windmill.py tests/test_synthetic_transaction_replay.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `python3 scripts/synthetic_transaction_replay.py --target restore-docker-runtime --dry-run`
- `uv run --with pyyaml python scripts/restore_verification.py --help`

## Live Rollout Notes

- The repository implementation is designed to run from `main` once the staging bridge remains available on `vmbr20`.
- The current repo does not ship a checked-in Prometheus or Alertmanager rule surface, so the stale-verification signal is currently exposed through Influx-backed Grafana status panels rather than a committed alert-rule file.
