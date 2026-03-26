# Workstream ADR 0163: Platform-Wide Retry Taxonomy And Exponential Backoff

- ADR: [ADR 0163](../adr/0163-platform-wide-retry-taxonomy-and-exponential-backoff.md)
- Title: shared retry classification, per-surface policy config, jittered backoff helpers, and runtime adoption for gateway, scheduler transport, NetBox sync, and NATS publication
- Status: merged
- Branch: `codex/adr-0163-retry-taxonomy`
- Worktree: `.worktrees/adr-0163`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0058-nats-event-bus`, `adr-0092-platform-api-gateway`, `adr-0119-budgeted-workflow-scheduler`
- Conflicts With: none
- Shared Surfaces: `platform/retry/`, `config/retry-policies.yaml`, `scripts/api_gateway/main.py`, `platform/scheduler/scheduler.py`, `scripts/netbox_inventory_sync.py`, `scripts/drift_lib.py`, `scripts/check_ad_hoc_retry.py`, `docs/runbooks/retry-taxonomy.md`

## Scope

- add `platform/retry/` with the canonical retry classes, error classification, per-surface policy loading, and sync plus async retry helpers
- add `config/retry-policies.yaml` as the repo-managed policy contract for `external_api`, `internal_api`, `ansible_ssh`, `nats_publish`, and `workflow_execution`
- migrate the API gateway's JWKS fetch, aggregate health probes, upstream OpenAPI fetches, safe proxied reads, and NATS request-event emission to the shared retry helpers
- migrate the scheduler Windmill transport reads and the NetBox inventory sync client to the shared retry helpers
- migrate shared NATS publication in `scripts/drift_lib.py` so downstream drift and restore tooling inherits the same backoff policy
- add `scripts/check_ad_hoc_retry.py` and wire it into `scripts/validate_repo.sh` so new ad hoc retry loops fail validation
- document the operator and implementation contract in `docs/runbooks/retry-taxonomy.md`

## Non-Goals

- retrofitting every existing Python HTTP call in one turn
- silently retrying non-idempotent mutation submissions that can double-execute before ADR 0165 idempotency keys land
- replacing Ansible module-level `retries:` usage where role-local convergence semantics are still the correct abstraction

## Expected Repo Surfaces

- `platform/retry/classification.py`
- `platform/retry/policy.py`
- `config/retry-policies.yaml`
- `scripts/api_gateway/main.py`
- `platform/scheduler/scheduler.py`
- `scripts/netbox_inventory_sync.py`
- `scripts/drift_lib.py`
- `scripts/check_ad_hoc_retry.py`
- `docs/runbooks/retry-taxonomy.md`
- `docs/workstreams/adr-0163-retry-taxonomy.md`

## Expected Live Surfaces

- the API gateway container on `docker-runtime-lv3` loads `/config/retry-policies.yaml`
- transient JWKS or upstream read failures on `api.lv3.org` are retried with bounded backoff instead of surfacing immediately
- API-gateway NATS request events tolerate short broker interruptions with bounded retry
- non-idempotent proxied writes remain single-shot until ADR 0165 supplies idempotency guarantees

## Verification

- `python3 scripts/check_ad_hoc_retry.py`
- `uv run --with pytest --with fastapi==0.116.1 --with httpx==0.28.1 --with uvicorn==0.35.0 --with pyyaml==6.0.2 --with cryptography==45.0.6 pytest -q tests/test_retry_policy.py tests/test_netbox_inventory_sync.py tests/test_api_gateway.py tests/unit/test_scheduler_budgets.py`
- `python3 scripts/api_gateway_catalog.py --validate`
- `scripts/validate_repo.sh retry-guard`

## Merge Criteria

- the shared retry helpers classify HTTP, socket, and timeout failures into the ADR taxonomy
- the gateway runtime consumes the shared retry policy config during converge
- safe read paths retry with bounded backoff while non-idempotent mutation paths remain single-shot
- the validation guard rejects new raw `time.sleep` retry loops outside `platform/retry/`

## Outcome

- repository implementation is complete on `main` in repo release `0.149.0`
- the repo now ships the shared retry taxonomy, per-surface retry config, API-gateway retry adoption, Windmill transport read retries, NetBox retry migration, shared NATS publication retries, and the ad hoc retry guard
- live apply is still pending because the documented Tailscale path and the public-IP fallback were unreachable from the execution environment during this turn
