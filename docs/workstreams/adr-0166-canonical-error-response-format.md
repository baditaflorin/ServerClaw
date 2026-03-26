# Workstream ADR 0166: Canonical Error Response Format And Error Code Registry

- ADR: [ADR 0166](../adr/0166-canonical-error-response-format-and-error-code-registry.md)
- Title: Shared canonical HTTP error envelopes and a repo-managed platform error-code registry
- Status: merged
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
- The first live-apply attempt on `2026-03-26` was blocked by controller-to-host SSH timeouts; public verification still showed `https://api.lv3.org/v1/health` returning the legacy `{"detail":"missing bearer token"}` payload, so the workstream is merged but not yet live applied.

## Notes For The Next Assistant

- Re-run the gateway and platform-context converges from `main` once controller access to `65.108.75.123:22` is stable again.
- After live apply succeeds, add an ADR 0166 receipt, update `versions/stack.yaml` platform evidence, and flip this workstream to `live_applied`.
