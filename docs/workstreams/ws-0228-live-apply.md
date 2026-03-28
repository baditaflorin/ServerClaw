# Workstream WS-0228: Windmill Default Operations Surface Live Apply

- ADR: [ADR 0228](../adr/0228-windmill-as-the-default-browser-and-api-operations-surface.md)
- Title: Make Windmill the default browser-first and API-first surface for repo-managed operations
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0228-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0228-live-apply`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0087-validation-gate`, `adr-0091-continuous-drift-detection`, `adr-0105-capacity-model`, `adr-0111-end-to-end-integration-test-suite`, `adr-0129-runbook-automation-executor`, `adr-0141-token-lifecycle-management`, `adr-0142-public-surface-security-scanning`
- Conflicts With: none
- Shared Surfaces: `collections/.../windmill_runtime/defaults/main.yml`, `collections/.../windmill_runtime/tasks/verify.yml`, `config/windmill/scripts/*.py`, `docs/runbooks/`, `docs/adr/0228-*.md`, `docs/adr/.index.yaml`, `tests/`, `workstreams.yaml`, `receipts/live-applies/`

## Scope

- seed every workflow-catalog Windmill wrapper into the `lv3` workspace so Windmill becomes the default browser and API operations surface for those governed tasks
- harden the remaining wrapper scripts that still assume controller-local import resolution or CLI-only output
- add a verification contract in the Windmill runtime role for the default operations surface
- document the default browser/API path and the representative live verification routes
- record workstream-local live-apply evidence without touching protected integration files unless this branch becomes the final mainline integration step

## Non-Goals

- publishing Windmill on the public edge
- enabling every possible schedule in one workstream
- redesigning the scheduler, command catalog, or API gateway contracts that already call into Windmill
- changing the protected release files before this branch explicitly becomes the final verified merge-to-main step

## Expected Repo Surfaces

- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/verify.yml`
- `config/windmill/scripts/nightly-integration-tests.py`
- `config/windmill/scripts/weekly-capacity-report.py`
- `config/windmill/scripts/collection-publish.py`
- `docs/runbooks/windmill-default-operations-surface.md`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/validation-gate.md`
- `docs/runbooks/drift-detection.md`
- `docs/runbooks/capacity-model.md`
- `docs/runbooks/integration-test-suite.md`
- `docs/adr/0228-windmill-as-the-default-browser-and-api-operations-surface.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0228-live-apply.md`
- `tests/test_nightly_integration_tests.py`
- `tests/test_weekly_capacity_report_windmill.py`
- `tests/test_windmill_default_operations_surface.py`

## Expected Live Surfaces

- the private Windmill workspace `lv3` exposes the workflow-catalog wrappers as seeded scripts instead of leaving them repo-only
- operators and agents can discover those operations through Windmill script metadata and execute representative safe workflows through the standard API routes
- the Windmill runtime converge verifies the default operations surface metadata in addition to the base healthcheck and validation-gate status scripts

## Verification

- `uv run --with pytest --with pyyaml pytest tests/test_nightly_integration_tests.py tests/test_weekly_capacity_report_windmill.py tests/test_ansible_collection_packaging.py tests/test_windmill_default_operations_surface.py -q`
- `python3 -m py_compile config/windmill/scripts/nightly-integration-tests.py config/windmill/scripts/weekly-capacity-report.py config/windmill/scripts/collection-publish.py`
- `make syntax-check-windmill`
- `./scripts/validate_repo.sh agent-standards`
- live verification:
  - `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/w/lv3/scripts/get/p/f%2Flv3%2Fweekly_capacity_report`
  - `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{"no_live_metrics":true}' http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fweekly_capacity_report`
  - `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{"dry_run":true}' http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Faudit_token_inventory`

## Notes For The Next Assistant

- `./scripts/validate_repo.sh agent-standards` should be run while this workstream still has `status: in_progress`; the final status flip to `live_applied` should happen after that branch-ownership check passes
- `docs/runbooks/windmill-default-operations-surface.md` is the central place for the representative seeded-script and API routes; avoid copying the whole catalog into every feature-specific runbook
- maintenance-window execution should stay documented as present-but-constrained until the live NATS publish authorization gap in `docs/runbooks/maintenance-windows.md` is closed
