# Workstream WS-0253: Unified Runtime Assurance Scoreboard Live Apply

- ADR: [ADR 0253](../adr/0253-unified-runtime-assurance-scoreboard-and-rollup.md)
- Title: Operator-facing runtime assurance scoreboard and service-environment rollup
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0253-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0253-live-apply`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal`, `adr-0113-world-state-materializer`, `adr-0209-use-case-services`, `adr-0244-runtime-assurance-matrix`
- Conflicts With: none
- Shared Surfaces: `scripts/ops_portal/`, `docs/adr/0244`, `docs/adr/0253`, `docs/runbooks/runtime-assurance-scoreboard.md`, `docs/adr/.index.yaml`, `workstreams.yaml`, `receipts/live-applies/`

## Scope

- compute one operator-facing runtime assurance rollup per active service and
  environment
- combine current health-composite data with publication metadata and
  receipt-backed evidence for route, smoke, auth, TLS, and logging dimensions
- render the new scoreboard inside the interactive ops portal and harden the
  live verification path so portal converges fail closed if the scoreboard is
  missing
- record live-apply evidence and ADR metadata without touching protected
  release files on this branch

## Non-Goals

- implementing every follow-on runtime assurance evidence source in this same
  workstream
- updating `README.md`, `VERSION`, `changelog.md`, or `versions/stack.yaml`
  before the final merge-to-main integration step
- redefining the gateway health-composite contract for unrelated consumers

## Expected Repo Surfaces

- `scripts/ops_portal/app.py`
- `scripts/ops_portal/runtime_assurance.py`
- `scripts/ops_portal/templates/partials/overview.html`
- `scripts/ops_portal/static/portal.css`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`
- `docs/runbooks/runtime-assurance-scoreboard.md`
- `docs/runbooks/ops-portal-down.md`
- `docs/adr/0244-runtime-assurance-matrix-per-service-and-environment.md`
- `docs/adr/0253-unified-runtime-assurance-scoreboard-and-rollup.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0253-live-apply.md`
- `workstreams.yaml`
- `tests/test_interactive_ops_portal.py`
- `tests/test_runtime_assurance_scoreboard.py`
- `receipts/live-applies/`

## Expected Live Surfaces

- `ops.lv3.org` renders a runtime assurance scoreboard that shows service and
  environment identity, per-dimension assurance state, evidence timestamps,
  owner, runbook, and next action
- the portal converge path verifies the scoreboard partial instead of proving
  only a generic shell render

## Verification

- `python3 -m py_compile scripts/ops_portal/app.py scripts/ops_portal/runtime_assurance.py`
- `uv run --with pytest --with fastapi==0.116.1 --with httpx==0.28.1 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest tests/test_interactive_ops_portal.py tests/test_runtime_assurance_scoreboard.py -q`
- `make syntax-check-ops-portal`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `./scripts/validate_repo.sh agent-standards`
- live verification from `docker-runtime-lv3`: the portal overview renders the
  runtime assurance section and the public `ops.lv3.org` surface still reaches
  the authenticated shell cleanly

## Mainline Integration

- when this workstream is merged to `main`, update the protected integration
  files only after the live apply is confirmed from `main`
- if the live apply succeeds on this branch, note the verified platform version
  in the ADR metadata here and in the receipt, but leave `versions/stack.yaml`
  and the top-level `README.md` status summary for the final integration step

## Notes For The Next Assistant

- the scoreboard is intentionally allowed to surface `unknown` dimensions; ADR
  0253 requires honest visibility for missing assurance rather than optimistic
  green rollups
- avoid moving the assurance builder outside `scripts/ops_portal/` unless the
  runtime role is also updated to sync the new shared module into production
