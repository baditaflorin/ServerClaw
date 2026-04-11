# Workstream WS-0245: Declared-To-Live Service Attestation Live Apply

- ADR: [ADR 0245](../adr/0245-declared-to-live-service-attestation.md)
- Title: declared-to-live service attestation through shared runtime evidence, gateway APIs, and ops-portal visibility
- Status: live_applied
- Implemented In Repo Version: 0.177.72
- Live Applied In Platform Version: 0.130.46
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0245-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0245-live-apply`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0113-world-state-materializer`, `adr-0123-service-uptime-contracts`, `adr-0244-runtime-assurance-matrix-per-service-and-environment`
- Conflicts With: none
- Shared Surfaces: `.repo-structure.yaml`, `platform/runtime_assurance/**`, `scripts/declared_live_attestation.py`, `scripts/api_gateway/main.py`, `scripts/ops_portal/**`, `scripts/validate_repo.sh`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/templates/Dockerfile.j2`, `tests/test_declared_live_attestation.py`, `tests/test_api_gateway.py`, `tests/test_interactive_ops_portal.py`, `tests/test_ops_portal_runtime_role.py`, `docs/adr/0245-declared-to-live-service-attestation.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-api-gateway.md`, `docs/runbooks/platform-operations-portal.md`, `docs/runbooks/validate-repository-automation.md`, `receipts/live-applies/2026-03-29-adr-0245-declared-to-live-service-attestation-live-apply.json`, `workstreams.yaml`

## Scope

- implement a shared declared-to-live attestation model for every active production service
- derive attestation from declared runtime metadata plus live witness sources that already exist on the platform
- expose the attestation through a repo-managed CLI entrypoint and the platform API gateway
- surface the attestation in the interactive ops portal so operators can inspect failures without reading raw JSON
- replay the live apply from this isolated worktree, record verification evidence in the branch, and then refresh the protected release files only during the final exact-main recut

## Non-Goals

- building the full ADR 0253 runtime-assurance scoreboard in this workstream
- rewriting protected release files before the final exact-main recut on the latest `origin/main` baseline
- claiming a new canonical platform version before the final merge-to-`main` step

## Expected Repo Surfaces

- `platform/runtime_assurance/**`
- `.repo-structure.yaml`
- `scripts/declared_live_attestation.py`
- `scripts/api_gateway/main.py`
- `scripts/ops_portal/**`
- `scripts/validate_repo.sh`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/templates/Dockerfile.j2`
- `tests/test_declared_live_attestation.py`
- `tests/test_api_gateway.py`
- `tests/test_interactive_ops_portal.py`
- `tests/test_ops_portal_runtime_role.py`
- `docs/adr/0245-declared-to-live-service-attestation.md`
- `docs/workstreams/ws-0245-live-apply.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-api-gateway.md`
- `docs/runbooks/platform-operations-portal.md`
- `docs/runbooks/validate-repository-automation.md`
- `receipts/live-applies/2026-03-29-adr-0245-declared-to-live-service-attestation-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- `api.example.com` exposes a repo-managed declared-to-live attestation API for the active production service catalog
- `ops.example.com` shows the attestation rollup and per-service witness details from the shared gateway contract
- branch-local attestation verification proves declared host binding, observed runtime identity, endpoint or route proof, and the latest successful assurance receipt for the affected production services

## Verification

- `uv run --with pytest --with fastapi==0.116.1 --with httpx==0.28.1 --with uvicorn==0.35.0 --with pyyaml==6.0.2 --with cryptography==45.0.6 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest -q tests/test_declared_live_attestation.py tests/test_api_gateway.py tests/test_interactive_ops_portal.py tests/test_ops_portal_runtime_role.py tests/test_config_merge_windmill.py tests/test_windmill_circuit_clients.py tests/test_windmill_operator_admin_app.py`
  returned `102 passed in 5.48s` on the latest `0.177.72` exact-main replay commit `b7f10ba204e98566e35e7c796918160b0a0a969c`.
- `python3 -m py_compile platform/runtime_assurance/declared_live_attestation.py scripts/declared_live_attestation.py scripts/api_gateway/main.py scripts/ops_portal/app.py scripts/ops_portal/runtime_assurance.py`,
  `make syntax-check-api-gateway`, and `make syntax-check-ops-portal` all passed on 2026-03-29.
- `make preflight WORKFLOW=converge-api-gateway` and `make preflight WORKFLOW=converge-ops-portal` both passed from this worktree on the same `0.177.72` replay commit.
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`, `./scripts/validate_repo.sh agent-standards`, `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`, and `git diff --check` all passed on the documented `0.177.72` state.
- `make validate` reported the same unrelated ansible-lint warnings in `control_plane_recovery`, `monitoring_vm`, `openbao_runtime`, and `windmill_runtime`, continued through the downstream idempotency, shell, JSON, compose runtime env guard, retry guard, repository data model, ADR 0230 policy, and architecture fitness steps, and then exited on the expected branch-local workstream surface ownership guard because branch `codex/ws-0245-live-apply` maps to terminal workstream `ws-0245-live-apply`.
- With explicit ADR 0153 service locks held for `vm:120/service:api_gateway` and `vm:120/service:ops_portal`, `make converge-api-gateway env=production ANSIBLE_TRACE_ARGS='-e bypass_promotion=true'` completed successfully from source commit `b7f10ba204e98566e35e7c796918160b0a0a969c` with recap `docker-runtime : ok=242 changed=111 unreachable=0 failed=0 skipped=35 rescued=0 ignored=0`.
- From the same source commit, `make converge-ops-portal env=production ANSIBLE_TRACE_ARGS='-e bypass_promotion=true'` completed successfully with recap `docker-runtime : ok=131 changed=17 unreachable=0 failed=0 skipped=14 rescued=0 ignored=0`.
- After that latest-main replay, public `https://api.example.com/healthz` returned `HTTP 200` with `{"status":"ok"}`, unauthenticated `HEAD https://api.example.com/v1/platform/attestation` returned `HTTP 401`, authenticated `GET https://api.example.com/v1/platform/attestation` returned `HTTP 200` with a `45`-service summary and `api_gateway` attested, authenticated `GET https://api.example.com/v1/platform/attestation/api_gateway` returned `HTTP 200` with `service_id=api_gateway` and `status=attested`, guest-local `http://127.0.0.1:8092/health` returned `HTTP 200` with `{"status":"ok"}`, guest-local `http://127.0.0.1:8092/` returned `HTTP 200` with `root_len=487865` and still contained `Runtime Assurance`, guest-local `http://127.0.0.1:8092/partials/overview` returned `HTTP 200` with `overview_len=403506` and still contained `Runtime Assurance`, guest-local `http://127.0.0.1:8092/partials/launcher` returned `HTTP 200` with `launcher_len=65756` and still contained `Application Launcher`, public `https://ops.example.com/health` returned `HTTP 200` with `{"status":"ok"}`, and public `https://ops.example.com/` returned `HTTP 302` to `/oauth2/sign_in`.

## Mainline Integration

- release `0.177.72` now records ADR 0245 in repository truth on top of the latest `origin/main` baseline, which also carries the ADR 0274 through ADR 0294 documentation additions
- the canonical live-apply receipt for this workstream is `receipts/live-applies/2026-03-29-adr-0245-declared-to-live-service-attestation-live-apply.json`
- the exact-main gateway and ops-portal replays are complete from committed source `b7f10ba204e98566e35e7c796918160b0a0a969c`, and the recorded receipt preserves the current mainline platform baseline at `0.130.46`
- no additional ADR-local merge blocker remains beyond integrating this exact latest-main replay into `origin/main`

## Notes For The Next Assistant

- the two live surfaces were re-verified on 2026-03-29 from the latest `origin/main` merge commit, but the `ops-portal` apply path remains shared with other active workstreams; re-check for concurrent applies and hold an ADR 0153 service lock before treating a replay interruption as an ADR 0245 regression
- the role hardening in `ops_portal_runtime` now matters for exact-worktree replay from separate macOS worktrees: it creates directory-backed receipt destinations before copy, syncs the shared `search_fabric` package explicitly, and preserves the package layout in the Docker build context
- stale local SSH port forwards such as `127.0.0.1:28092` can hide a healthy guest-local portal; when in doubt, verify `http://127.0.0.1:8092` over the current Proxmox jump path instead of relying on an old forward
