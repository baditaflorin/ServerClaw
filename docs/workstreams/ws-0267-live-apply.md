# Workstream WS-0267: Expiring Gate Bypass Waivers Live Apply

- ADR: [ADR 0267](../adr/0267-expiring-gate-bypass-waivers-with-structured-reason-codes.md)
- Title: Govern validation-gate bypasses as expiring waivers with structured reason codes
- Status: in_progress
- Branch: `codex/ws-0267-gate-bypass-waivers-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0267-gate-bypass-waivers`
- Owner: codex
- Depends On: `adr-0087-validation-gate`, `adr-0168-automated-validation`, `adr-0228-windmill-default-operations-surface`, `adr-0230-policy-decisions-via-open-policy-agent-and-conftest`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0267-live-apply.md`, `docs/adr/0267-*.md`, `docs/adr/.index.yaml`, `docs/runbooks/validation-gate.md`, `docs/runbooks/platform-release-management.md`, `.config-locations.yaml`, `.githooks/pre-push`, `config/gate-bypass-waiver-catalog.json`, `config/validation-gate.json`, `config/workflow-catalog.json`, `docs/schema/gate-bypass-waiver-*.json`, `scripts/gate_bypass_waivers.py`, `scripts/gate_status.py`, `scripts/log_gate_bypass.py`, `scripts/release_manager.py`, `scripts/validate_repository_data_models.py`, `collections/.../windmill_runtime/defaults/main.yml`, `collections/.../windmill_runtime/tasks/verify.yml`, `tests/`, `receipts/live-applies/*adr-0267*`

## Scope

- replace vague validation-gate bypass receipts with governed waivers that carry reason taxonomy, substitute evidence, owner, expiry, and remediation references
- summarize open waivers plus repeated expired reasons in both `gate-status` and release-readiness views
- keep the seeded Windmill gate-status workflow and worker checkout integrity sentinel aligned with the new waiver policy surface
- record branch-local live-apply evidence and verification without touching protected release files until the final merge-to-main step

## Non-Goals

- redesigning the full validation-gate manifest or the remote-build execution model
- rewriting historical legacy receipts into the new governed format
- changing unrelated release or README canonical-truth surfaces before the final mainline integration step

## Expected Repo Surfaces

- `.githooks/pre-push`
- `.config-locations.yaml`
- `config/gate-bypass-waiver-catalog.json`
- `config/validation-gate.json`
- `config/workflow-catalog.json`
- `docs/schema/gate-bypass-waiver-catalog.schema.json`
- `docs/schema/gate-bypass-waiver-receipt.schema.json`
- `scripts/gate_bypass_waivers.py`
- `scripts/gate_status.py`
- `scripts/log_gate_bypass.py`
- `scripts/release_manager.py`
- `scripts/validate_repository_data_models.py`
- `docs/runbooks/validation-gate.md`
- `docs/runbooks/platform-release-management.md`
- `docs/adr/0267-expiring-gate-bypass-waivers-with-structured-reason-codes.md`
- `docs/adr/.index.yaml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/verify.yml`
- `tests/test_gate_bypass_waivers.py`
- `tests/test_validation_gate.py`
- `tests/test_release_manager.py`
- `tests/test_windmill_operator_admin_app.py`

## Expected Live Surfaces

- the shared `f/lv3/gate-status` Windmill path returns waiver-summary fields alongside the manifest, last-run, and post-merge status data
- the Windmill worker checkout refreshes when the new waiver catalog or summary helper changes
- the live repo checkout on `docker-runtime-lv3` can execute `make gate-status` with the governed waiver summary visible

## Ownership Notes

- keep shared release files (`VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`, release notes, and `RELEASE.md`) untouched on this branch until the final exact-main integration step
- if the live apply succeeds before merge-to-main, record the receipts and note precisely which protected integration files remain for main

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_validation_gate.py tests/test_gate_bypass_waivers.py tests/test_release_manager.py tests/test_windmill_operator_admin_app.py -q`
- `python3 -m py_compile scripts/gate_bypass_waivers.py scripts/log_gate_bypass.py scripts/gate_status.py scripts/release_manager.py`
- `python3 scripts/gate_bypass_waivers.py --summary --format json`
- `python3 scripts/gate_status.py --format json`
- `uv run --with pyyaml python scripts/release_manager.py status --timeout 0`
- `./scripts/validate_repo.sh agent-standards`
- `./scripts/validate_repo.sh data-models`
- `make gate-status`
- `make converge-windmill`

## Merge Criteria

- the governed bypass path requires structured waiver fields and writes ADR-0267-compliant receipts
- `gate-status` and `release status` both summarize open waivers plus repeated expired reasons
- the Windmill seeded gate-status verification proves the new summary fields on the live platform
- the final exact-main integration records which release files and platform version updates were applied from `main`

## Notes For The Next Assistant

- historical receipts under `receipts/gate-bypasses/` remain legacy evidence; do not retrofit them unless a dedicated cleanup ADR takes ownership
- the worker checkout integrity sentinel now has to cover both `scripts/gate_bypass_waivers.py` and `config/gate-bypass-waiver-catalog.json` or the live Windmill surface can drift silently
