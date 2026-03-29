# Workstream WS-0245: Declared-To-Live Service Attestation Live Apply

- ADR: [ADR 0245](../adr/0245-declared-to-live-service-attestation.md)
- Title: declared-to-live service attestation through shared runtime evidence, gateway APIs, and ops-portal visibility
- Status: live_applied
- Implemented In Repo Version: 0.177.67
- Live Applied In Platform Version: 0.130.46
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0245-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0245-live-apply`
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

- `api.lv3.org` exposes a repo-managed declared-to-live attestation API for the active production service catalog
- `ops.lv3.org` shows the attestation rollup and per-service witness details from the shared gateway contract
- branch-local attestation verification proves declared host binding, observed runtime identity, endpoint or route proof, and the latest successful assurance receipt for the affected production services

## Verification

- `uv run --with pytest --with fastapi==0.116.1 --with httpx==0.28.1 --with uvicorn==0.35.0 --with pyyaml==6.0.2 --with cryptography==45.0.6 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest -q tests/test_declared_live_attestation.py tests/test_api_gateway.py tests/test_interactive_ops_portal.py tests/test_ops_portal_runtime_role.py tests/test_config_merge_windmill.py tests/test_windmill_circuit_clients.py tests/test_windmill_operator_admin_app.py`
  returned `92 passed in 6.75s` on the final `0.177.67` exact-main candidate after the latest `origin/main` merge carried ADR 0238 on top of the earlier ADR 0245 integration work.
- `python3 -m py_compile platform/runtime_assurance/declared_live_attestation.py scripts/declared_live_attestation.py scripts/api_gateway/main.py scripts/ops_portal/app.py scripts/ops_portal/runtime_assurance.py`,
  `make syntax-check-api-gateway`, and `make syntax-check-ops-portal` all passed on 2026-03-29.
- `make preflight WORKFLOW=converge-api-gateway` and `make preflight WORKFLOW=converge-ops-portal` both passed from this worktree on the final `0.177.67` candidate.
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`, `./scripts/validate_repo.sh agent-standards`, `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`, and `git diff --check` all passed on the final `0.177.67` candidate state.
- `make validate` progressed past the earlier `config/ansible-role-idempotency.yml` failure once `harbor_runtime` was added to the tracked-role registry, then exited on seven unrelated ansible-lint warnings in `control_plane_recovery`, `monitoring_vm`, `openbao_runtime`, and `windmill_runtime` that pre-existed this ADR 0245 workstream.
- The repo-managed API gateway live replay completed successfully with final recap `docker-runtime-lv3 : ok=234 changed=106 unreachable=0 failed=0 skipped=37 rescued=0 ignored=0`, and the live gateway then verified `HTTP 401` for unauthenticated `GET /v1/platform/attestation` plus authenticated `HTTP 200` for both `/v1/platform/attestation` and `/v1/platform/attestation/api_gateway`.
- The live attestation payload for `api_gateway` proved the declared runtime witness, route witness, and receipt witness, and the authenticated summary showed the shared production attestation rollup under the new contract.
- The live ops portal verified `HTTP 200` for `http://127.0.0.1:8092/health`, `HTTP 200` for `http://127.0.0.1:8092/`, `HTTP 200` for `http://127.0.0.1:8092/partials/overview`, and `HTTP 302` for public `https://ops.lv3.org/` back to the expected `/oauth2/sign_in` path.
- Concurrent controller-side applies from other workstreams on the shared `ops-portal` surface interrupted the outer repo-managed replay path during this workstream. The final live state was recovered by syncing the exact branch Dockerfile, portal application files, and templates into `/opt/ops-portal/service` on `docker-runtime-lv3`, rebuilding with `docker compose --file /opt/ops-portal/docker-compose.yml up -d --build --force-recreate --remove-orphans`, and then re-verifying the internal and public portal surfaces end to end.
- The first exact-main gateway replay from committed source `a639fe4fc477722aec1cc84cfe3a62e68273ce7b` failed only at the final Keycloak bearer-token verification step even though `https://api.lv3.org/healthz` still returned `HTTP 200` and the same `lv3-agent-hub` client credentials still issued bearer tokens successfully against the realm. The immediate retry from the same committed source then completed successfully with `make converge-api-gateway env=production ANSIBLE_TRACE_ARGS='-e bypass_promotion=true'` reporting `docker-runtime-lv3 : ok=242 changed=111 unreachable=0 failed=0 skipped=35 rescued=0 ignored=0`.
- The exact-main ops-portal replay from committed source `a639fe4fc477722aec1cc84cfe3a62e68273ce7b` completed successfully with `make converge-ops-portal env=production ANSIBLE_TRACE_ARGS='-e bypass_promotion=true'` reporting `docker-runtime-lv3 : ok=129 changed=17 unreachable=0 failed=0 skipped=14 rescued=0 ignored=0`.
- After that exact-main replay, public `https://api.lv3.org/healthz` returned `HTTP 200`, unauthenticated `HEAD https://api.lv3.org/v1/platform/attestation` returned `HTTP 401`, authenticated `GET /v1/platform/attestation` returned a `45`-service summary with `api_gateway` attested, authenticated `GET /v1/platform/attestation/api_gateway` returned `HTTP 200` with `service_id=api_gateway` and `status=attested`, guest-local `http://127.0.0.1:8092/health` returned `HTTP 200` with `{"status":"ok"}`, guest-local `http://127.0.0.1:8092/` returned `HTTP 200` with `root_len=420303` and still contained `Runtime Assurance`, guest-local `http://127.0.0.1:8092/partials/overview` returned `HTTP 200` with `overview_len=403590` and still contained `Runtime Assurance`, public `https://ops.lv3.org/health` returned `HTTP 200`, and public `https://ops.lv3.org/` returned `HTTP 302` to `/oauth2/sign_in`.

## Mainline Integration

- release `0.177.67` now records ADR 0245 in repository truth on top of the refreshed `origin/main` baseline that already carried ADR 0238 at `0.177.66`
- the canonical live-apply receipt for this workstream is `receipts/live-applies/2026-03-29-adr-0245-declared-to-live-service-attestation-live-apply.json`
- the exact-main gateway and ops-portal replays are complete from committed source `a639fe4fc477722aec1cc84cfe3a62e68273ce7b`, and the recorded receipt preserves the current mainline platform baseline at `0.130.46`

## Notes For The Next Assistant

- the two live surfaces were verified on 2026-03-29, but the `ops-portal` apply path is shared with other active workstreams; re-check for concurrent applies before treating a replay interruption as an ADR 0245 regression
- the role hardening in `ops_portal_runtime` now matters for exact-worktree replay from separate macOS worktrees: it creates directory-backed receipt destinations before copy, syncs the shared `search_fabric` package explicitly, and preserves the package layout in the Docker build context
