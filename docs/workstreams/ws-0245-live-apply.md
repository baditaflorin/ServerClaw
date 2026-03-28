# Workstream ws-0245-live-apply: ADR 0245 Live Apply From Latest `origin/main`

- ADR: [ADR 0245](../adr/0245-declared-to-live-service-attestation.md)
- Title: declared-to-live service attestation through shared runtime evidence, gateway APIs, and ops-portal visibility
- Status: in_progress
- Branch: `codex/ws-0245-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0245-live-apply`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0113-world-state-materializer`, `adr-0123-service-uptime-contracts`, `adr-0244-runtime-assurance-matrix-per-service-and-environment`
- Conflicts With: none
- Shared Surfaces: `platform/runtime_assurance/**`, `scripts/declared_live_attestation.py`, `scripts/api_gateway/main.py`, `scripts/ops_portal/**`, `tests/test_declared_live_attestation.py`, `tests/test_api_gateway.py`, `tests/test_interactive_ops_portal.py`, `docs/adr/0245-declared-to-live-service-attestation.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-api-gateway.md`, `docs/runbooks/platform-operations-portal.md`, `docs/runbooks/validate-repository-automation.md`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- implement a shared declared-to-live attestation model for every active production service
- derive attestation from declared runtime metadata plus live witness sources that already exist on the platform
- expose the attestation through a repo-managed CLI entrypoint and the platform API gateway
- surface the attestation in the interactive ops portal so operators can inspect failures without reading raw JSON
- replay the live apply from this isolated worktree and record verification evidence in the branch without touching protected release files

## Non-Goals

- building the full ADR 0253 runtime-assurance scoreboard in this workstream
- changing `VERSION`, `changelog.md`, top-level `README.md`, or `versions/stack.yaml` on the workstream branch
- claiming a new canonical platform version before the final merge-to-`main` step

## Expected Repo Surfaces

- `platform/runtime_assurance/**`
- `scripts/declared_live_attestation.py`
- `scripts/api_gateway/main.py`
- `scripts/ops_portal/**`
- `tests/test_declared_live_attestation.py`
- `tests/test_api_gateway.py`
- `tests/test_interactive_ops_portal.py`
- `docs/adr/0245-declared-to-live-service-attestation.md`
- `docs/workstreams/ws-0245-live-apply.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-api-gateway.md`
- `docs/runbooks/platform-operations-portal.md`
- `docs/runbooks/validate-repository-automation.md`
- `receipts/live-applies/2026-03-28-adr-0245-declared-to-live-service-attestation-live-apply.json`
- `receipts/live-applies/evidence/2026-03-28-adr-0245-declared-to-live-service-attestation-production.json`
- `workstreams.yaml`

## Expected Live Surfaces

- `api.lv3.org` exposes a repo-managed declared-to-live attestation API for the active production service catalog
- `ops.lv3.org` shows the attestation rollup and per-service witness details from the shared gateway contract
- branch-local attestation verification proves declared host binding, observed runtime identity, endpoint or route proof, and the latest successful assurance receipt for the affected production services

## Verification

- `uv run --with pytest --with fastapi==0.116.1 --with httpx==0.28.1 --with uvicorn==0.35.0 --with pyyaml==6.0.2 --with cryptography==45.0.6 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest -q tests/test_declared_live_attestation.py tests/test_api_gateway.py tests/test_interactive_ops_portal.py`
- `python3 -m py_compile scripts/declared_live_attestation.py scripts/api_gateway/main.py scripts/ops_portal/app.py`
- `uv run --with pyyaml python3 scripts/declared_live_attestation.py --repo-root . --format json`
- `make syntax-check-api-gateway`
- `make syntax-check-ops-portal`
- `./scripts/validate_repo.sh agent-standards`
- `make validate`
- live apply the changed services from this worktree and verify the declared-to-live contract through the live gateway and ops portal surfaces

## Merge Criteria

- active production services emit a deterministic attestation record with concrete witness evidence
- edge-published services require separate route proof in addition to runtime presence proof
- the branch records the live-apply receipt, ADR metadata, and merge-to-main notes needed for a safe later integration

## Notes

- protected integration files stay untouched on this workstream branch even if the live apply is fully verified
- update this document with concrete command transcripts, receipts, and merge-to-main leftovers once the implementation and replay complete
