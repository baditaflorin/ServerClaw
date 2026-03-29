# Workstream WS-0244: Runtime Assurance Matrix Live Apply

- ADR: [ADR 0244](../adr/0244-runtime-assurance-matrix-per-service-and-environment.md)
- Title: Implement and live-apply one service-by-environment runtime assurance matrix using existing health, route, and verification evidence
- Status: live_applied
- Implemented In Repo Version: pending main merge
- Live Applied In Platform Version: `0.130.44` context on the branch-local replay; canonical mainline bump still pending
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
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
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `tests/test_runtime_assurance.py`
- `tests/test_api_gateway.py`
- `tests/test_api_gateway_runtime_role.py`
- `tests/test_interactive_ops_portal.py`
- `tests/test_ops_portal_runtime_role.py`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/tasks/verify.yml`
- `receipts/live-applies/2026-03-29-adr-0244-runtime-assurance-matrix-live-apply.json`
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

## Verification

- The focused validation slice passed from this worktree: `46 passed in 17.12s` for `tests/test_runtime_assurance.py`, `tests/test_runtime_assurance_scoreboard.py`, `tests/test_api_gateway.py`, `tests/test_api_gateway_runtime_role.py`, `tests/test_interactive_ops_portal.py`, and `tests/test_ops_portal_runtime_role.py`.
- `uv run --with pyyaml --with jsonschema --with nats-py==2.11.0 python3 scripts/runtime_assurance.py --validate --print-report-json`, `PYTHON_BIN=/opt/homebrew/bin/python3 uvx --from pyyaml python scripts/ansible_scope_runner.py validate`, `make syntax-check-api-gateway`, and `./scripts/validate_repo.sh agent-standards` all passed from the isolated worktree.
- The branch-local live replay on `docker-runtime-lv3` corrected both the portal and gateway service trees, removed stale metadata sidecars, and rebuilt the live containers until the authenticated gateway route and the portal matrix matched the branch state.
- Internal verification on `2026-03-29` confirmed `http://127.0.0.1:8083/healthz` returned `{"status":"ok"}`, the authenticated `GET /v1/platform/runtime-assurance` call returned `HTTP 200` with `45` bindings (`7` pass / `38` degraded), and `http://127.0.0.1:8092/partials/runtime-assurance` rendered the same governed summary without a degraded-data banner.
- Public edge verification on `2026-03-29` confirmed `https://ops.lv3.org/` still returned `HTTP 302` to `/oauth2/sign_in` with the expected hardening headers after the live replay.
- The outer `make converge-ops-portal` and `make syntax-check-ops-portal` paths still hit local `SIGTERM` / `143` behavior from the Codex execution environment before completion. The branch records that wrapper limitation explicitly because the targeted role tests, validation slices, and live runtime verification all succeeded.

## Mainline Integration

- Protected integration files still pending the merge-to-`main` step are `README.md`, `VERSION`, the release sections in `changelog.md`, `docs/release-notes/README.md`, the next numbered release note, `versions/stack.yaml`, and `build/platform-manifest.json`.
- During the final mainline integration, `versions/stack.yaml` should advance the `api_gateway` and `ops_portal` latest-receipt pointers to `2026-03-29-adr-0244-runtime-assurance-matrix-live-apply` and record the canonical repo/platform version truth from the merged replay.
- The canonical branch-local evidence for this live replay is `receipts/live-applies/2026-03-29-adr-0244-runtime-assurance-matrix-live-apply.json`.

## Notes For The Next Assistant

- The portal now ignores unreadable `._*.json` and `.DS_Store` receipt sidecars instead of crashing while enumerating live-apply or drift evidence.
- The API gateway runtime role now has to ship `scripts/runtime_assurance.py` and copy it into the container image; without that helper the rebuilt gateway falls into a restart loop with `ModuleNotFoundError: No module named 'runtime_assurance'`.
- If the full outer `make converge-ops-portal` path is re-tested outside Codex, compare its result against this receipt before treating the local `143` termination as a platform regression.
