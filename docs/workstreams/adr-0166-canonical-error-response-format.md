# Workstream ADR 0166: Canonical Error Response Format And Error Code Registry

- ADR: [ADR 0166](../adr/0166-canonical-error-response-format-and-error-code-registry.md)
- Title: Shared canonical HTTP error envelopes and a repo-managed platform error-code registry
- Status: live_applied
- Branch: `codex/live-apply-0166`
- Worktree: `.worktrees/live-apply-0166`
- Owner: codex
- Depends On: `adr-0017-adr-lifecycle`, `adr-0037-schema-validation`, `adr-0070-rag-platform-context`, `adr-0092-platform-api-gateway`
- Conflicts With: none
- Shared Surfaces: `config/error-codes.yaml`, `scripts/canonical_errors.py`, `scripts/api_gateway/main.py`, `scripts/platform_context_service.py`, `docs/runbooks/platform-api-error-codes.md`, `versions/stack.yaml`

## Scope

- define the shared platform error registry in `config/error-codes.yaml`
- add reusable canonical error helpers in `scripts/canonical_errors.py`
- convert the API gateway to canonical error envelopes with request trace ids and OpenAPI registry hints
- convert the platform-context API to canonical error envelopes with trace ids
- validate the registry through the repository data-model gate
- document the contract for future platform HTTP services

## Non-Goals

- retrofitting every existing third-party upstream service behind the gateway
- changing successful response schemas for gateway or platform-context endpoints
- introducing a separate external error-management service

## Expected Repo Surfaces

- `config/error-codes.yaml`
- `scripts/canonical_errors.py`
- `scripts/api_gateway/main.py`
- `scripts/platform_context_service.py`
- `scripts/validate_repository_data_models.py`
- `docs/runbooks/platform-api-error-codes.md`
- `docs/adr/0166-canonical-error-response-format-and-error-code-registry.md`
- `docs/workstreams/adr-0166-canonical-error-response-format.md`

## Expected Live Surfaces

- `https://api.lv3.org/v1/health` rejects anonymous callers with canonical code `AUTH_TOKEN_MISSING`
- gateway validation and dependency failures return registry-backed envelopes with `trace_id`
- platform-context protected endpoints return canonical auth and validation failures
- the deployed runtime bundles `config/error-codes.yaml` and `scripts/canonical_errors.py`

## Verification

- run `uv run --with pytest --with fastapi==0.116.1 --with httpx==0.28.1 --with uvicorn==0.35.0 --with pyyaml==6.0.2 --with cryptography==45.0.6 --with qdrant-client==1.15.1 --with sentence-transformers==5.1.0 pytest -q tests/test_canonical_errors.py tests/test_api_gateway.py tests/test_platform_context_service.py`
- run `uv run --with jsonschema python scripts/validate_repository_data_models.py --validate`
- run `make syntax-check-api-gateway`
- run `make syntax-check-rag-context`
- verify the live gateway and platform-context endpoints after converge from `main`

## Merge Criteria

- the shared registry is validated in-repo
- both repo-managed APIs emit canonical envelopes for auth, validation, resource, dependency, and unexpected failures
- the operator runbook documents the registry and envelope contract
- the live platform is re-converged from `main` and verified on the real endpoints

## Outcome

- Repo implementation completed for release `0.162.0` on `2026-03-26`.
- Unit and integration-focused repository tests passed for the canonical error helpers, API gateway, and platform-context service.
- The 2026-03-26 live replay from `main` now applies ADR 0166 on both production HTTP surfaces: `https://api.lv3.org/v1/health` returns the canonical `AUTH_TOKEN_MISSING` envelope publicly, and `http://100.64.0.1:8010/v1/platform-summary` returns the same canonical envelope on the private platform-context path.
- The final platform-context recovery required a direct guest-side rebuild because the Tailscale-routed Ansible converge stalled mid corpus sync before `config/error-codes.yaml` reached `/opt/platform-context/corpus/config/`; after copying the missing registry file and rebuilding the container, authenticated rebuild and query verification succeeded with `2550` indexed chunks.

## Notes For The Next Assistant

- If the public host SSH path to `65.108.75.123:22` remains unstable, prefer the steady-state Tailscale host path (`ops@100.64.0.1`) plus the governed Proxmox guest jump when replaying `docker-runtime-lv3` services.
- The live-apply receipt records the manual recovery used to finish this rollout; future replays should come back to the full repo-managed `rag-context` converge once the intermittent guest copy stall is understood.
