# Workstream ws-0187-live-apply: ADR 0187 Live Apply From Latest `origin/main`

- ADR: [ADR 0187](../adr/0187-anonymized-seed-data-snapshots-for-repeatable-tests.md)
- Title: live implementation, publication, and verification of anonymized seed snapshots for repeatable tests
- Status: mainline live applied
- Branch: `codex/ws-0187-live-apply`
- Worktree: `.worktrees/ws-0187-live-apply`
- Owner: codex
- Depends On: `adr-0088-ephemeral-fixtures`, `adr-0099-backup-restore-verification`, `adr-0185-branch-scoped-ephemeral-preview-environments`
- Conflicts With: none
- Shared Surfaces: `config/seed-data-catalog.json`, `scripts/seed_data_snapshots.py`, `scripts/fixture_manager.py`, `scripts/restore_verification.py`, `collections/ansible_collections/lv3/platform/roles/backup_vm/`, `docs/runbooks/seed-data-snapshots.md`, `receipts/live-applies/`

## Scope

- add the repo-managed seed snapshot catalog and deterministic anonymized dataset builder
- publish snapshots onto the managed `backup-lv3` store through committed automation
- wire `tiny`, `standard`, and `recovery` staging into ephemeral fixtures and restore verification
- validate the repo automation, rerun the live path from merged `main`, and record the final integration evidence

## Verification

- `uv run --with pytest python -m pytest tests/test_seed_data_snapshots.py tests/test_fixture_manager.py tests/test_restore_verification.py tests/test_restore_verification_windmill.py tests/test_vmid_allocator.py -q`
- `./scripts/validate_repo.sh data-models`
- `./scripts/validate_repo.sh agent-standards`
- `make syntax-check-backup-vm`
- `make seed-snapshot-build SEED_CLASS=tiny`
- `make seed-snapshot-build SEED_CLASS=standard`
- `make seed-snapshot-build SEED_CLASS=recovery`
- `make seed-snapshot-verify SEED_CLASS=tiny SNAPSHOT_ID=tiny-4927754bef12`
- `make configure-backup-vm`
- `make seed-snapshot-publish SEED_CLASS=tiny SNAPSHOT_ID=tiny-4fc40ef2f916`
- `make seed-snapshot-publish SEED_CLASS=standard SNAPSHOT_ID=standard-c81d5e556889`
- `make seed-snapshot-publish SEED_CLASS=recovery SNAPSHOT_ID=recovery-7028dc9df835`
- `uv run --with pyyaml python scripts/seed_data_snapshots.py verify --seed-class tiny --snapshot-id tiny-4fc40ef2f916 --remote`
- `uv run --with pyyaml python scripts/seed_data_snapshots.py verify --seed-class standard --snapshot-id standard-c81d5e556889 --remote`
- `uv run --with pyyaml python scripts/seed_data_snapshots.py verify --seed-class recovery --snapshot-id recovery-7028dc9df835 --remote`
- `BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 make configure-backup-vm env=production`
- `TF_VAR_proxmox_endpoint=https://127.0.0.1:18006/api2/json LV3_PROXMOX_API_INSECURE=true LV3_PROXMOX_HOST_ADDR=100.64.0.1 python3 scripts/fixture_manager.py create seed-staging-smoke --purpose ws-0187-live-apply --policy integration-test --seed-class tiny --seed-snapshot-id tiny-4fc40ef2f916 --json`
- `uv run --with pyyaml python scripts/restore_verification.py --seed-class tiny --seed-snapshot-id tiny-4fc40ef2f916 --print-report-json`

## Outcome

- Passed:
  - `backup-lv3` now manages `/var/lib/lv3/seed-data-snapshots/{tiny,standard,recovery}` through the committed `backup_vm` role, and the merged-main replay `BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 make configure-backup-vm env=production` completed successfully from the integrated branch state.
  - Deterministic anonymized seed snapshots were built locally and published live to:
    - `tiny/tiny-4fc40ef2f916`
    - `standard/standard-c81d5e556889`
    - `recovery/recovery-7028dc9df835`
  - Remote checksum verification passed for all three published snapshots on `backup-lv3`.
  - The fixture and restore-verification automation surfaces were both advanced far enough live to expose and fix several real repo issues:
    - `fixture_manager.py` now honors endpoint-only API overrides, supports controller-side insecure HTTPS for tunneled Proxmox API access, understands the ADR 0106 `capacity-model.json.reservations[].kind=ephemeral_pool` shape, preserves local module paths inside the Docker Tofu fallback, forwards `TF_VAR_*` values into the container, rewrites loopback Proxmox endpoints for Docker via `host.docker.internal`, and prefers `LV3_PROXMOX_HOST_ADDR` for the SSH jump host.
    - A reusable `tests/fixtures/seed-staging-smoke-fixture.yml` fixture was added so seed staging can be exercised against the live `lv3-debian-base` template (`9000`) without depending on the richer `lv3-ops-base` template catalog.
- Blocked by unrelated live platform gaps:
  - `fixture_manager.py create ops-base` still cannot complete end to end on the live host because template `lv3-ops-base` (`9003`) is not currently present on Proxmox even though it remains declared in `config/vm-template-manifest.json`.
  - `fixture_manager.py create seed-staging-smoke` now clones and boots a live VM that is SSH-reachable, but the older OpenTofu Proxmox provider path can still hang in `Creating...` after the clone already exists; the repo helper can therefore reach a real guest but cannot finish the fixture receipt path until that separate provider wait issue is resolved everywhere the legacy path still appears.
  - `restore_verification.py --seed-class tiny` progressed live through restored VM lifecycle management (`900` then `901`) and QEMU guest-agent access, but restored-guest SSH banner exchange remained slow enough that the full workflow did not produce a receipt during the live-apply session.
- Merge-to-main status:
  - The integrated truth updates, release bump, and mainline live-apply receipt are completed on the dedicated main-merge branch for safe merge to `main`.
  - No extra shared-file follow-up remains beyond keeping the non-ADR blocker notes above visible until the template-catalog and restored-guest SSH issues are addressed separately.
