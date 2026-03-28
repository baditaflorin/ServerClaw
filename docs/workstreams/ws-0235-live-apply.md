# Workstream WS-0235: Cross-Application Launcher Live Apply

- ADR: [ADR 0235](../adr/0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher.md)
- Title: Cross-application launcher and favorites via a PatternFly-style shared masthead launcher in the interactive ops portal
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0235-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0235-live-apply`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal`, `adr-0152-homepage`, `adr-0209-use-case-services`, `adr-0234-shared-human-app-shell-and-navigation-via-patternfly`
- Conflicts With: none
- Shared Surfaces: `scripts/ops_portal/`, `config/service-capability-catalog.json`, `config/workflow-catalog.json`, `config/persona-catalog.json`, `docs/runbooks/platform-operations-portal.md`, `tests/test_interactive_ops_portal.py`, `workstreams.yaml`, `docs/adr/0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher.md`, `receipts/live-applies/`

## Scope

- add a shared masthead launcher to the interactive ops portal as the first live implementation of ADR 0235
- render launcher destinations from canonical service, publication, workflow, and persona metadata instead of hard-coded bookmark lists
- support search, favorites, and recent destinations in a way that can be verified through repo tests and live platform checks
- document the operator usage and leave merge-to-main integration notes explicit if protected release files must wait

## Non-Goals

- rewriting every first-party surface into a full PatternFly application in one workstream
- changing the protected release files on this workstream branch unless this branch becomes the final merge-to-main integration step
- replacing Homepage or third-party product-native interfaces

## Expected Repo Surfaces

- `docs/adr/0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0235-live-apply.md`
- `docs/runbooks/platform-operations-portal.md`
- `.config-locations.yaml`
- `config/service-capability-catalog.json`
- `config/workflow-catalog.json`
- `config/persona-catalog.json`
- `docs/schema/persona-catalog.schema.json`
- `scripts/ops_portal/app.py`
- `scripts/ops_portal/static/portal.css`
- `scripts/ops_portal/templates/base.html`
- `scripts/ops_portal/templates/index.html`
- `scripts/service_catalog.py`
- `scripts/validate_repository_data_models.py`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`
- `tests/test_interactive_ops_portal.py`
- `tests/test_validate_service_catalog.py`
- `workstreams.yaml`
- `receipts/live-applies/2026-03-28-adr-0235-cross-application-launcher-live-apply.json`

## Expected Live Surfaces

- `https://ops.lv3.org` exposes the shared application launcher in the masthead
- the launcher groups destinations by purpose, allows persona-aware filtering, and records favorites plus recent destinations
- favorites and recents can be re-verified against the live portal session without ad hoc server edits

## Verification Plan

- `uv run --with pytest --with pyyaml --with fastapi==0.116.1 --with httpx==0.28.1 --with cryptography==45.0.6 --with PyJWT==2.10.1 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest tests/test_interactive_ops_portal.py tests/test_validate_service_catalog.py tests/test_ops_portal.py -q`
- `python3 -m py_compile scripts/ops_portal/app.py scripts/service_catalog.py scripts/validate_repository_data_models.py`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `make syntax-check-ops-portal`
- `./scripts/validate_repo.sh agent-standards`
- live verification through the production ops portal session and a fresh live-apply receipt

## Integration Notes

- protected integration files must stay untouched on this branch unless the workstream becomes the final verified merge-to-main step
- if the change is fully live applied before merge, record the receipt here and note the remaining `main`-only updates explicitly
