# ADR 0163: Platform-Wide Retry Taxonomy and Exponential Backoff

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

Error handling across the platform is inconsistent and ad hoc. A survey of the current codebase reveals three distinct, independent retry implementations:

- **`scripts/netbox_inventory_sync.py`**: linear backoff with `sleep(2)` between attempts, `max_attempts=5`, retries on HTTP 500+ and URLErrors only.
- **`platform/scheduler/scheduler.py`**: a single `max_restarts` field per workflow (default 1), no backoff, no error classification.
- **`scripts/api_gateway/main.py`**: no retry at all — timeouts propagate to the caller immediately.
- **All NATS publish calls**: fire-and-forget, no retry on broker unavailability.
- **OpenBao API calls**: no retry, any transient network error returns `500 Internal Server Error` to the caller.

The consequence is that transient failures — a 50ms TCP hiccup on the Proxmox host's internal bridge, a JWKS endpoint that takes 3 seconds to respond during a Keycloak GC pause, a Windmill API that returns `503` during a rolling restart — all surface as hard failures. Agents receive a hard error, escalate to the operator, and the operator must manually retry something that would have succeeded on the second attempt.

There is also the inverse problem: code that retries indiscriminately (any error → retry N times) causes three problems:
1. **Permanent errors are retried pointlessly.** A misconfigured workflow that returns `400 Bad Request` every time will be retried N times before being escalated, consuming time and resources on a failure that cannot be fixed by retrying.
2. **Load amplification.** During a service outage, every caller retrying simultaneously creates a thundering herd that worsens the outage.
3. **No jitter.** The existing `sleep(2)` calls mean that if 10 agents encounter the same transient error simultaneously, they all retry at the same moment — the second burst hits a service that may still be recovering.

The correct model is a **retry taxonomy** that classifies every error by its retryability and applies exponential backoff with full jitter for retryable errors.

## Decision

We will define a **platform-wide error taxonomy** and a **standard retry policy implementation** in `platform/retry/policy.py` that is used by all platform code.

### Error taxonomy

Every error at every platform layer maps to one of four retry classes:

| Class | Code | Meaning | Retry behaviour |
|---|---|---|---|
| `TRANSIENT` | T | Infrastructure hiccup; likely succeeds on immediate retry | Retry immediately up to 2 times; then escalate to BACKOFF |
| `BACKOFF` | B | Service temporarily overloaded or recovering | Exponential backoff with jitter; retry up to `max_attempts` |
| `PERMANENT` | P | Logic error or invalid input; retrying cannot help | Do not retry; escalate immediately |
| `FATAL` | F | Unrecoverable system failure; retry would be harmful | Do not retry; abort and page operator |

### Error classification

```python
# platform/retry/classification.py

ERROR_TAXONOMY: dict[str, RetryClass] = {
    # HTTP status codes
    "http:408": RetryClass.TRANSIENT,   # Request Timeout
    "http:429": RetryClass.BACKOFF,     # Too Many Requests (honour Retry-After header)
    "http:500": RetryClass.BACKOFF,     # Internal Server Error
    "http:502": RetryClass.BACKOFF,     # Bad Gateway (upstream restarting)
    "http:503": RetryClass.BACKOFF,     # Service Unavailable
    "http:504": RetryClass.BACKOFF,     # Gateway Timeout
    "http:400": RetryClass.PERMANENT,   # Bad Request
    "http:401": RetryClass.PERMANENT,   # Unauthorized (credential issue; retrying won't fix it)
    "http:403": RetryClass.PERMANENT,   # Forbidden
    "http:404": RetryClass.PERMANENT,   # Not Found
    "http:409": RetryClass.PERMANENT,   # Conflict (intent; manual resolution required)
    "http:422": RetryClass.PERMANENT,   # Unprocessable Entity (schema error)

    # Network errors
    "net:connection_refused":    RetryClass.BACKOFF,
    "net:connection_timeout":    RetryClass.TRANSIENT,
    "net:read_timeout":          RetryClass.BACKOFF,
    "net:ssl_error":             RetryClass.PERMANENT,  # cert mismatch is not transient
    "net:dns_resolution_failed": RetryClass.BACKOFF,

    # Platform-specific errors
    "platform:lock_contention":   RetryClass.BACKOFF,    # Lock held by another agent
    "platform:budget_exceeded":   RetryClass.PERMANENT,  # Budget violation; retry won't help
    "platform:health_gate_fail":  RetryClass.BACKOFF,    # Target unhealthy; wait for recovery
    "platform:concurrency_limit": RetryClass.BACKOFF,    # Windmill busy; back off
    "platform:intent_conflict":   RetryClass.PERMANENT,  # Semantic conflict; needs resolution
    "platform:circuit_open":      RetryClass.BACKOFF,    # Circuit breaker open (ADR 0164)

    # Ansible/SSH errors
    "ansible:unreachable":        RetryClass.BACKOFF,    # SSH transient failure
    "ansible:syntax_error":       RetryClass.PERMANENT,  # Playbook bug; retrying won't fix it
    "ansible:task_failed":        RetryClass.PERMANENT,  # Task returned non-zero; needs diagnosis
    "ansible:timeout":            RetryClass.BACKOFF,    # Ansible connection timeout
}
```

### Retry policy implementation

```python
# platform/retry/policy.py

import random
import time
from dataclasses import dataclass, field

@dataclass
class RetryPolicy:
    max_attempts:   int   = 5
    base_delay_s:   float = 1.0     # Initial delay for BACKOFF errors
    max_delay_s:    float = 60.0    # Cap on exponential growth
    multiplier:     float = 2.0     # Exponential growth factor
    jitter:         bool  = True    # Full jitter (prevents thundering herd)
    transient_max:  int   = 2       # TRANSIENT errors retry at most this many times immediately

DEFAULT_POLICY = RetryPolicy()

def with_retry(
    fn: Callable,
    policy: RetryPolicy = DEFAULT_POLICY,
    error_context: str = "",
) -> Any:
    """
    Execute fn with the platform retry policy. Classifies each exception
    and applies the appropriate backoff strategy.
    """
    last_error = None
    transient_count = 0

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return fn()
        except PlatformError as e:
            last_error = e
            retry_class = classify_error(e)

            if retry_class == RetryClass.PERMANENT:
                raise  # Never retry; surface immediately

            if retry_class == RetryClass.FATAL:
                ledger.write(event_type="platform.fatal_error", metadata={"error": str(e), "context": error_context})
                nats.publish("platform.alerts.fatal", {"error": str(e)})
                raise

            if retry_class == RetryClass.TRANSIENT:
                transient_count += 1
                if transient_count > policy.transient_max:
                    # Escalate transient → backoff after max immediate retries
                    retry_class = RetryClass.BACKOFF
                else:
                    # Retry immediately, no sleep
                    continue

            if retry_class == RetryClass.BACKOFF:
                if attempt >= policy.max_attempts:
                    break
                raw_delay = min(
                    policy.base_delay_s * (policy.multiplier ** (attempt - 1)),
                    policy.max_delay_s,
                )
                delay = random.uniform(0, raw_delay) if policy.jitter else raw_delay
                # Honour Retry-After header if present
                if hasattr(e, 'retry_after') and e.retry_after:
                    delay = max(delay, e.retry_after)
                time.sleep(delay)

    raise MaxRetriesExceeded(
        f"Exhausted {policy.max_attempts} attempts for {error_context}",
        last_error=last_error,
    )
```

### Per-surface default policies

Different platform surfaces warrant different default policies:

```yaml
# config/retry-policies.yaml

policies:
  - surface: external_api          # Hetzner, Anthropic, external webhooks
    max_attempts: 5
    base_delay_s: 2.0
    max_delay_s: 120.0
    multiplier: 2.0
    jitter: true

  - surface: internal_api          # Keycloak, OpenBao, Windmill (same host)
    max_attempts: 4
    base_delay_s: 0.5
    max_delay_s: 30.0
    multiplier: 2.0
    jitter: true

  - surface: ansible_ssh           # SSH connections to VMs
    max_attempts: 3
    base_delay_s: 5.0
    max_delay_s: 30.0
    multiplier: 2.0
    jitter: false                  # No jitter; SSH retries are expected to be sequential

  - surface: nats_publish          # NATS publish
    max_attempts: 3
    base_delay_s: 0.1
    max_delay_s: 5.0
    multiplier: 2.0
    jitter: true

  - surface: workflow_execution    # Full workflow retry (replaces max_restarts)
    max_attempts: 2
    base_delay_s: 10.0
    max_delay_s: 60.0
    multiplier: 2.0
    jitter: true
```

### Migration of existing retry code

| Existing pattern | Migration |
|---|---|
| `netbox_inventory_sync.py` linear backoff | Replace with `with_retry(fn, policy=INTERNAL_API_POLICY)` |
| `scheduler.py` `max_restarts=1` | Replace with `workflow_execution` surface policy |
| `api_gateway/main.py` no retry | Add `with_retry` around upstream proxy calls |
| All NATS publish calls | Wrap with `nats_publish` surface policy |
| All OpenBao API calls | Wrap with `internal_api` surface policy |

A Gitea Actions CI check (`scripts/check_ad_hoc_retry.py`) scans for raw `time.sleep` calls in retry loops and `for i in range(N)` retry patterns, failing the build if they are found outside of `platform/retry/`.

## Consequences

**Positive**

- Transient failures (TCP hiccups, JWKS slow response, brief NATS unavailability) are absorbed automatically without agent escalation. The operator is not paged for a 50ms network blip.
- Full jitter eliminates thundering herds. Ten agents all encountering the same transient error at T+0 will retry at T+rand(0, 1s), T+rand(0, 2s), etc., spreading the retry load.
- Permanent errors are surfaced immediately without wasting time on futile retries. A misconfigured workflow ID returns a `PERMANENT` error on the first attempt and escalates, not after N retry cycles.

**Negative / Trade-offs**

- Error classification is a code-time decision. A `net:connection_refused` is classified as `BACKOFF`, but if the service is permanently removed, it will back off N times before escalating. Miscellaneous infrastructure errors that look transient but are actually permanent will waste time on retries.
- The taxonomy requires ongoing maintenance as new error types are added. A new service that returns custom error codes must have those codes added to `ERROR_TAXONOMY` or they will default to `PERMANENT` (the safe fallback).

## Boundaries

- This ADR covers the retry behaviour for calls made by platform code. It does not govern Ansible's built-in `retries:` directive (which is handled in individual task definitions) or Windmill's own job retry mechanism (which is controlled by the workflow engine).
- The `FATAL` class triggers immediate operator paging. It must be used sparingly — only for genuinely unrecoverable states (e.g., OpenBao seal detected, Postgres WAL corruption). Overuse of `FATAL` will desensitise the operator.

## Related ADRs

- ADR 0044: Windmill (workflow_execution surface policy replaces max_restarts)
- ADR 0058: NATS event bus (nats_publish surface policy)
- ADR 0092: Platform API gateway (external proxy calls wrapped with retry)
- ADR 0115: Event-sourced mutation ledger (platform.fatal_error events)
- ADR 0119: Budgeted workflow scheduler (max_restarts replaced by retry taxonomy)
- ADR 0164: Circuit breaker pattern (circuit_open error class feeds into retry taxonomy)
- ADR 0170: Platform-wide timeout hierarchy (timeouts feed into retry classification)
