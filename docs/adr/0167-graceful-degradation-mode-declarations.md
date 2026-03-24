# ADR 0167: Graceful Degradation Mode Declarations

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

Every service in the platform depends on other services. When a dependency is unavailable, the current behaviour is undefined: some services crash, some hang, some silently return stale data, and some return ambiguous errors. There is no documented or tested answer to "what does the platform do when Postgres is down?" or "what happens if Keycloak is unreachable for 5 minutes?"

Observed current behaviours (undefined, not designed):
- **Windmill** with Postgres down: the Windmill API returns `500 Internal Server Error` on all requests. Active jobs stall. The error message does not indicate Postgres as the cause.
- **API gateway** with Keycloak down: JWT validation fails for every request after the JWKS cache (300-second TTL) expires. The response is `401 Unauthorized`, giving the caller no indication that the failure is temporary.
- **Agent sessions** with NATS down: NATS publish calls fail, but the `with_retry` logic retries until the retry limit, then the agent's session is aborted. The agent does not distinguish "NATS is temporarily unavailable" from "the intent was rejected."
- **OpenBao** during Proxmox host maintenance: the Tailscale proxy to OpenBao is unreachable. All workflows that need secrets fail immediately. There is no cached secret fallback.

In contrast, a well-designed system explicitly declares:
1. Which dependencies are **hard** (service cannot operate at all without them).
2. Which dependencies are **soft** (service degrades but remains partially functional).
3. What "degraded mode" looks like for each soft dependency failure.
4. What the recovery path is (how the service knows when to restore full function).

Without these declarations, every dependency failure is an unplanned outage. With them, dependency failures become planned, tested, expected degradations.

## Decision

We will add a **degradation mode declaration** to every service's entry in the service capability catalog (ADR 0075), and implement the declared degradation behaviour in each service.

### Degradation declaration schema

```yaml
# config/service-capability-catalog.json — degradation section per service

{
  "service_id": "api-gateway",
  "degradation_modes": [
    {
      "dependency": "keycloak",
      "dependency_type": "soft",
      "degraded_behaviour": "Use cached JWKS for JWT validation until TTL expires (300s). After TTL, return GATE_CIRCUIT_OPEN with retry_after=30 for all requests requiring auth.",
      "degraded_for_seconds_max": 300,
      "recovery_signal": "keycloak circuit closes (ADR 0164)",
      "tested_by": "fault:keycloak-unavailable"
    },
    {
      "dependency": "nats",
      "dependency_type": "soft",
      "degraded_behaviour": "Buffer NATS publish events in platform.nats_outbox (Postgres). All API request processing continues. Buffered events are flushed when NATS reconnects.",
      "degraded_for_seconds_max": -1,   # -1 = indefinite (Postgres outbox persists)
      "recovery_signal": "nats circuit closes (ADR 0164)",
      "tested_by": "fault:nats-unavailable"
    }
  ]
}

{
  "service_id": "windmill",
  "degradation_modes": [
    {
      "dependency": "postgres",
      "dependency_type": "hard",
      "degraded_behaviour": "Windmill cannot operate without Postgres. All job submissions fail with INFRA_DEPENDENCY_DOWN. Active jobs in memory continue until completion; they cannot persist state.",
      "degraded_for_seconds_max": 0,
      "recovery_signal": "Windmill reconnects to Postgres on its internal reconnect loop (15s interval)",
      "tested_by": "fault:postgres-unavailable"
    }
  ]
}

{
  "service_id": "platform-api",
  "degradation_modes": [
    {
      "dependency": "openbao",
      "dependency_type": "soft",
      "degraded_behaviour": "Cached secrets are served for up to 15 minutes (secret_cache_ttl_s: 900). After cache expiry, workflows that require uncached secrets are queued (not failed) until OpenBao reconnects.",
      "degraded_for_seconds_max": 900,
      "recovery_signal": "openbao circuit closes (ADR 0164)",
      "tested_by": "fault:openbao-unavailable"
    },
    {
      "dependency": "windmill",
      "dependency_type": "soft",
      "degraded_behaviour": "Intent submissions are queued in the intent queue (ADR 0155). Platform API returns EXEC_INTENT_QUEUED (202) instead of immediate submission.",
      "degraded_for_seconds_max": -1,
      "recovery_signal": "windmill circuit closes (ADR 0164)",
      "tested_by": "fault:windmill-unavailable"
    }
  ]
}
```

### Degradation mode classification

| `dependency_type` | Meaning | Service behaviour when dependency fails |
|---|---|---|
| `hard` | Service cannot function at all | Return `INFRA_DEPENDENCY_DOWN` immediately; no partial operation |
| `soft` | Service degrades but continues partially | Switch to declared `degraded_behaviour`; log degradation event |
| `optional` | Service operates fully without the dependency | Log a warning; no behaviour change |

### Secret cache implementation (OpenBao degradation)

The platform's secret cache holds a read-through, TTL-expiring copy of recently-read secrets:

```python
# platform/secrets/cache.py

SECRET_CACHE_TTL_S = 900  # 15 minutes; matches degradation declaration

class CachedSecretClient:
    def __init__(self, openbao: OpenBaoClient, cache_ttl_s: int = SECRET_CACHE_TTL_S):
        self._openbao = openbao
        self._cache: dict[str, CacheEntry] = {}

    def get(self, path: str) -> str:
        cached = self._cache.get(path)
        if cached and not cached.is_expired():
            return cached.value

        try:
            value = self._openbao.get(path)
            self._cache[path] = CacheEntry(value=value, fetched_at=now(), ttl_s=self._cache_ttl_s)
            return value
        except (CircuitOpenError, ConnectionError):
            if cached:
                # Serve stale cached value during OpenBao unavailability
                ledger.write("platform.secrets.serving_cached", {"path": path, "age_s": cached.age_s()})
                return cached.value
            # No cached value — queue the caller; cannot proceed
            raise PlatformError(
                error_code="INFRA_DEPENDENCY_DOWN",
                message=f"OpenBao unavailable and no cached value for {path}.",
                retry_advice="backoff",
                retry_after_s=30,
            )
```

### NATS outbox implementation (NATS degradation)

When NATS is unavailable, events are written to `platform.nats_outbox`:

```python
# platform/events/publisher.py

class ResilientNATSPublisher:
    def publish(self, subject: str, payload: dict):
        try:
            nats_circuit.call(lambda: self._nats.publish(subject, encode(payload)))
        except CircuitOpenError:
            # Buffer in Postgres outbox
            db.execute("""
                INSERT INTO platform.nats_outbox (subject, payload, buffered_at)
                VALUES (:subject, :payload, now())
            """, subject=subject, payload=json.dumps(payload))

    def flush_outbox(self):
        """Called when NATS circuit closes. Flushes buffered events in order."""
        events = db.query(
            "SELECT * FROM platform.nats_outbox ORDER BY buffered_at ASC FOR UPDATE SKIP LOCKED"
        )
        for event in events:
            self._nats.publish(event.subject, event.payload)
            db.execute("DELETE FROM platform.nats_outbox WHERE id=:id", id=event.id)
```

A NATS circuit `closed` event triggers `flush_outbox()` via the circuit breaker callback.

### Degradation mode health composite contribution

The health composite index (ADR 0128) includes a `degraded_mode` signal. A service operating in degraded mode is not `healthy` — it is `degraded` — even if its own health probe returns 200:

```python
# In health composite computation
if service.is_in_degraded_mode():
    signals["degraded_mode"] = HealthSignal(
        status="degraded",
        weight=0.3,
        detail=f"Operating in degraded mode: {service.active_degradation.degraded_behaviour[:100]}",
    )
```

### Degradation mode events

When a service enters or exits degraded mode, it publishes:
- `platform.service.degraded` (entering degraded mode)
- `platform.service.restored` (exiting degraded mode)

Both events are written to the mutation ledger and posted to Mattermost `#platform-ops`.

## Consequences

**Positive**

- Every service failure now has a documented, expected outcome. When Postgres is down for maintenance, operators know Windmill will fail hard (hard dependency), and the platform API will queue intents (soft dependency). Nothing is a surprise.
- The secret cache and NATS outbox convert previously hard failures (OpenBao unavailable → all workflows fail; NATS unavailable → all events lost) into soft degradations with bounded impact.
- Degradation declarations in the capability catalog feed the fault injection suite (ADR 0171), which validates that each declared degraded behaviour is actually what happens.

**Negative / Trade-offs**

- The secret cache serves stale secrets for up to 15 minutes during an OpenBao outage. If a secret was rotated just before the outage, the cached version is already stale and any service using it will fail. The 15-minute TTL is a balance; shorter TTLs reduce staleness risk but also reduce the degradation window.
- Hard dependencies cannot be made soft without architectural changes. Windmill requires Postgres; this is fundamental to its architecture. The declaration is documentation of reality, not a prescription for change.

## Boundaries

- Degradation mode declarations are documented and tested for platform-layer dependencies (service-to-service). Application-level dependencies (e.g., NetBox depending on its own Postgres schema) are governed by the application's own health probe and not by this ADR.
- The secret cache is only for platform secrets (OpenBao paths used by platform workflows). Application secrets (e.g., NetBox's database password) are loaded at application startup; their caching behaviour is application-specific.

## Related ADRs

- ADR 0043: OpenBao (secret source; CachedSecretClient wraps the OpenBao client)
- ADR 0058: NATS event bus (outbox pattern for NATS degradation)
- ADR 0075: Service capability catalog (degradation_modes field added)
- ADR 0128: Platform health composite index (degraded_mode signal)
- ADR 0164: Circuit breaker pattern (circuit events trigger degradation mode transitions)
- ADR 0171: Controlled fault injection (validates each declared degraded behaviour)
