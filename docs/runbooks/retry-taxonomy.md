# Retry Taxonomy

## Purpose

Use the shared retry taxonomy when platform code calls a networked dependency and must distinguish between transient, backoff-worthy, permanent, and fatal failures.

## Canonical Sources

- policy config: [config/retry-policies.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/retry-policies.yaml)
- implementation: [platform/retry/classification.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/retry/classification.py)
- implementation: [platform/retry/policy.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/retry/policy.py)
- validation guard: [scripts/check_ad_hoc_retry.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/check_ad_hoc_retry.py)

## Retry Classes

| Class | Meaning | Behaviour |
| --- | --- | --- |
| `TRANSIENT` | short-lived transport hiccup | retry immediately up to `transient_max`, then escalate into backoff |
| `BACKOFF` | dependency unavailable or overloaded | exponential backoff with optional jitter |
| `PERMANENT` | invalid input or logic bug | fail immediately |
| `FATAL` | retry would be harmful | abort immediately |

## Default Surfaces

- `external_api`: third-party APIs and public webhooks
- `internal_api`: Keycloak, Windmill, API-gateway upstream reads, NetBox sync
- `ansible_ssh`: SSH and other sequential host-connectivity retries
- `nats_publish`: broker connection and publish attempts
- `workflow_execution`: reserved for higher-level workflow retries once ADR 0165 idempotency keys make submission replay safe

## Implementation Rules

Use `with_retry(...)` for synchronous callers and `async_with_retry(...)` for async callers.

```python
from platform.retry import async_with_retry, policy_for_surface

payload = await async_with_retry(
    lambda: client.get(url, timeout=10),
    policy=policy_for_surface("internal_api"),
    error_context="keycloak jwks fetch",
)
```

Avoid wrapping non-idempotent mutation submissions unless the target supports replay safety. For current LV3 code this means:

- safe to retry: GET, HEAD, OPTIONS, NATS connect/publish, health probes, JWKS fetches
- keep single-shot for now: workflow submissions, deploy webhooks, secret-rotation webhooks, arbitrary proxied writes without an idempotency key

## Validation

Run the focused guard directly:

```bash
python3 scripts/check_ad_hoc_retry.py
```

Or through the shared repository validator:

```bash
scripts/validate_repo.sh retry-guard
```

## Updating The Taxonomy

1. Add the new error code in `platform/retry/classification.py`.
2. Add or adjust the surface defaults in `config/retry-policies.yaml` if the new caller needs a different envelope.
3. Add a regression test proving the classification and retry behaviour.
4. Migrate the caller to `with_retry(...)` or `async_with_retry(...)`.
