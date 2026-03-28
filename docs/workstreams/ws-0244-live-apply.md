# Workstream WS-0244: Runtime Assurance Matrix Live Apply

- ADR: [ADR 0244](../adr/0244-runtime-assurance-matrix-per-service-and-environment.md)
- Title: Implement and live-apply one service-by-environment runtime assurance matrix using existing health, route, and verification evidence
- Status: in_progress
- Branch: `codex/ws-0244-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0244-live-apply`
- Owner: codex
- Depends On: `adr-0064-health-probes`, `adr-0075-service-capability-catalog`, `adr-0092-api-gateway`, `adr-0093-interactive-ops-portal`, `adr-0113-world-state-materializer`, `adr-0123-uptime-contracts`, `adr-0133-portal-auth-default`, `adr-0142-public-surface-scan`, `adr-0169-structured-logs`, `adr-0190-synthetic-replay`, `adr-0214-prod-staging-cells`, `ws-0244-runtime-assurance-adrs`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0244-runtime-assurance-matrix-per-service-and-environment.md`, `docs/adr/.index.yaml`, `docs/runbooks/runtime-assurance-matrix.md`, `config/runtime-assurance-matrix.json`, `docs/schema/runtime-assurance-matrix.schema.json`, `scripts/runtime_assurance.py`, `scripts/validate_repository_data_models.py`, `scripts/api_gateway/main.py`, `scripts/ops_portal/app.py`, `scripts/ops_portal/templates/index.html`, `scripts/ops_portal/templates/partials/runtime_assurance.html`, `tests/test_runtime_assurance.py`, `tests/test_api_gateway.py`, `tests/test_api_gateway_runtime_role.py`, `tests/test_interactive_ops_portal.py`, `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/tasks/verify.yml`, `receipts/live-applies/2026-03-28-adr-0244-runtime-assurance-matrix-live-apply.json`, `workstreams.yaml`

## Scope

- define the governed runtime-assurance matrix shape per service and per environment
- derive an operator-facing rollup from existing declared and observed evidence instead of relying on ad hoc manual checks
- expose the runtime-assurance view through the existing platform API and ops portal surfaces
- live-apply the affected control-plane services from the latest `origin/main`-based worktree and verify the new assurance path end to end
- record merge-safe branch-local evidence, ADR metadata, and workstream state without touching protected release files on this branch

## Non-Goals

- claiming ADR 0245 through ADR 0253 are all fully implemented when this workstream only consumes the evidence already available on the platform
- rewriting `README.md`, `VERSION`, release sections in `changelog.md`, or `versions/stack.yaml` before the final mainline integration step
- introducing manual-only platform mutations that are not captured in repo automation or the live-apply receipt

## Expected Repo Surfaces

- `docs/adr/0244-runtime-assurance-matrix-per-service-and-environment.md`
- `docs/workstreams/ws-0244-live-apply.md`
- `docs/runbooks/runtime-assurance-matrix.md`
- `docs/adr/.index.yaml`
- `config/runtime-assurance-matrix.json`
- `docs/schema/runtime-assurance-matrix.schema.json`
- `scripts/runtime_assurance.py`
- `scripts/validate_repository_data_models.py`
- `scripts/api_gateway/main.py`
- `scripts/ops_portal/app.py`
- `scripts/ops_portal/templates/index.html`
- `scripts/ops_portal/templates/partials/runtime_assurance.html`
- `tests/test_runtime_assurance.py`
- `tests/test_api_gateway.py`
- `tests/test_api_gateway_runtime_role.py`
- `tests/test_interactive_ops_portal.py`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/tasks/verify.yml`
- `receipts/live-applies/2026-03-28-adr-0244-runtime-assurance-matrix-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- the runtime assurance matrix is available from the repo-managed platform control surface on `docker-runtime-lv3`
- the live ops portal exposes the new runtime assurance rollup without requiring ad hoc operator data assembly
- a fresh live-apply receipt records the evidence sources and post-apply verification for ADR 0244 from the latest `origin/main` baseline

## Verification Plan

- validate the new runtime-assurance catalog and service-catalog contracts locally
- run targeted pytest coverage for the matrix, API, and portal surfaces
- run the repository validation gates required by ADR 0168 and the normal pre-push path
- converge the affected control-plane surface on the live platform from this worktree
- verify the API and browser/operator views against the live platform and capture the evidence in a structured receipt

## Merge Criteria

- ADR 0244 is no longer a documentation-only intention and has a concrete repo-managed matrix plus rollup
- the live platform exposes the new runtime-assurance data through the normal operator control plane
- branch-local evidence is clear about what became true live and what protected integration updates still wait for merge to `main`
