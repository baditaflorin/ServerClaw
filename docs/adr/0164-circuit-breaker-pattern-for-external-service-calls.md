# ADR 0164: Circuit Breaker Pattern for External Service Calls

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform makes synchronous calls to several external and internal services on the critical path of agent execution:

- **Keycloak** (`sso.lv3.org`): JWT validation on every API gateway request; JWKS refresh every 300 seconds.
- **OpenBao** (Proxmox host, Tailscale-only): Secret reads at workflow start and during rotation.
- **Windmill** (`docker-runtime-lv3`): Job submission and status polling for every intent execution.
- **Hetzner DNS API** (external): DNS record updates during subdomain provisioning.
- **NATS** (`docker-runtime-lv3`): Every platform event publication.
- **Anthropic/Ollama API**: Every LLM inference call in agent workflows.

The current error handling model (ADR 0163 retry taxonomy) handles transient failures well: a single timeout triggers exponential backoff and retries. But it does not handle **service outages** well: if Keycloak is restarting for 90 seconds, every API gateway request will attempt a connection, wait for the timeout (10 seconds), retry (2–3 more times with backoff), and then fail — with each caller independently spending 30+ seconds discovering that Keycloak is down. This is 30 seconds of wasted latency multiplied by every concurrent request.

The correct model for service outages is the **circuit breaker pattern**:
- **CLOSED** (normal): calls pass through; failures are counted.
- **OPEN** (outage detected): calls fail immediately without attempting a connection; no timeout wait.
- **HALF-OPEN** (probe): after a recovery window, one probe request is allowed through; if it succeeds, the circuit closes.

A circuit breaker converts "wait 30 seconds to discover Keycloak is down on every request" into "fail immediately after the first 5 failures discover Keycloak is down."

## Decision

We will implement a **circuit breaker** for every external and high-impact internal service call in the platform, backed by NATS JetStream KV for distributed state so that all agents share a single circuit state.

### Circuit breaker state machine

```
  CLOSED ──(failure_threshold exceeded)──→ OPEN
    ↑                                         │
    └──(probe succeeds)── HALF_OPEN ←──(recovery_window elapsed)──┘
```

### Distributed circuit state

Circuit state is shared across all agents via NATS JetStream KV:

```python
# platform/circuit/breaker.py

CIRCUIT_KV_BUCKET = "platform.circuits"

@dataclass
class CircuitState:
    name: str                  # Circuit identifier: e.g., "keycloak", "openbao"
    state: str                 # "closed" | "open" | "half_open"
    failure_count: int
    last_failure_at: datetime
    opened_at: datetime | None
    recovery_window_s: int
    failure_threshold: int
    success_threshold: int     # Consecutive successes in HALF_OPEN to close
    consecutive_successes: int

class CircuitBreaker:

    def __init__(self, name: str, policy: CircuitPolicy):
        self.name = name
        self.policy = policy
        self.kv = nats.kv_bucket(CIRCUIT_KV_BUCKET)

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        state = self._load_state()

        if state.state == "open":
            if self._should_attempt_probe(state):
                self._transition(state, "half_open")
            else:
                raise CircuitOpenError(
                    circuit=self.name,
                    opened_at=state.opened_at,
                    retry_after=state.recovery_window_s,
                )

        try:
            result = fn(*args, **kwargs)
            self._record_success(state)
            return result
        except Exception as e:
            self._record_failure(state, e)
            raise

    def _record_failure(self, state: CircuitState, exc: Exception):
        state.failure_count += 1
        state.last_failure_at = now()
        state.consecutive_successes = 0
        if state.failure_count >= state.policy.failure_threshold:
            self._transition(state, "open")
            nats.publish(f"platform.circuit.opened.{self.name}", {
                "circuit": self.name,
                "failure_count": state.failure_count,
                "opened_at": state.opened_at.isoformat(),
            })
        self._save_state(state)

    def _record_success(self, state: CircuitState):
        if state.state == "half_open":
            state.consecutive_successes += 1
            if state.consecutive_successes >= state.policy.success_threshold:
                self._transition(state, "closed")
                nats.publish(f"platform.circuit.closed.{self.name}", {"circuit": self.name})
        elif state.state == "closed":
            # Reset failure count on success
            if state.failure_count > 0:
                state.failure_count = max(0, state.failure_count - 1)
        self._save_state(state)
```

### Circuit policy per service

```yaml
# config/circuit-policies.yaml

circuits:
  - name: keycloak
    service: Keycloak OIDC / JWKS
    failure_threshold: 5        # 5 consecutive failures → open
    recovery_window_s: 30       # Try one probe after 30 seconds
    success_threshold: 2        # 2 consecutive probe successes → close
    timeout_s: 10               # Per-call timeout before counting as failure

  - name: openbao
    service: OpenBao secret store
    failure_threshold: 3        # OpenBao failures are critical; open sooner
    recovery_window_s: 20
    success_threshold: 1
    timeout_s: 5

  - name: windmill
    service: Windmill workflow engine
    failure_threshold: 5
    recovery_window_s: 60       # Windmill restarts take longer
    success_threshold: 2
    timeout_s: 15

  - name: nats
    service: NATS event bus
    failure_threshold: 10       # NATS is local; should be highly available
    recovery_window_s: 10
    success_threshold: 3
    timeout_s: 2

  - name: hetzner_dns
    service: Hetzner DNS API (external)
    failure_threshold: 3
    recovery_window_s: 120      # External API; longer recovery window
    success_threshold: 2
    timeout_s: 30

  - name: anthropic_api
    service: Anthropic Claude API
    failure_threshold: 3
    recovery_window_s: 300      # API outages last minutes
    success_threshold: 1
    timeout_s: 60

  - name: ollama
    service: Ollama local inference
    failure_threshold: 5
    recovery_window_s: 30
    success_threshold: 2
    timeout_s: 120              # Local inference can be slow; generous timeout
```

### Integration points

Every platform call to an external/internal service is wrapped in a circuit breaker:

```python
# platform/identity/keycloak.py
keycloak_circuit = CircuitBreaker("keycloak", load_policy("keycloak"))

def validate_jwt(token: str) -> Claims:
    return keycloak_circuit.call(_validate_jwt_inner, token)

# platform/secrets/openbao.py
openbao_circuit = CircuitBreaker("openbao", load_policy("openbao"))

def get_secret(path: str) -> str:
    return openbao_circuit.call(_get_secret_inner, path)
```

### Circuit open behaviour per service

When a circuit opens, the platform does not simply fail — it degrades gracefully (ADR 0167):

| Circuit | `OPEN` behaviour |
|---|---|
| `keycloak` | API gateway serves `503 Service Unavailable` with `Retry-After: 30`. Ops portal uses cached session for read-only access. |
| `openbao` | Workflows that need secrets are queued (ADR 0155), not immediately run. Cached secrets (TTL-bounded, ADR 0167) are used for read-only access. |
| `windmill` | Intents are queued in the intent queue (ADR 0155); no new jobs submitted until circuit closes. |
| `nats` | Events are buffered in Postgres `platform.nats_outbox` and flushed when circuit closes. |
| `hetzner_dns` | DNS operations are queued; platform logs a finding that DNS changes are delayed. |
| `anthropic_api` | LLM calls fall back to local Ollama (ADR 0145); if Ollama also fails, non-LLM degraded mode. |
| `ollama` | LLM calls use external Anthropic API; if that circuit is also open, LLM calls return `ServiceUnavailable`. |

### Circuit state in the coordination map

The real-time agent coordination map (ADR 0161) includes the current circuit breaker state for all registered circuits, giving operators immediate visibility into which services are degraded:

```
CIRCUIT BREAKERS                    2026-03-24 14:32:01
  keycloak          ● CLOSED    failures: 0/5
  openbao           ● CLOSED    failures: 0/3
  windmill          ● CLOSED    failures: 0/5
  nats              ● CLOSED    failures: 0/10
  hetzner_dns       ○ OPEN      opened: 2m ago  recovery in: 58s
  anthropic_api     ● CLOSED    failures: 1/3
  ollama            ● CLOSED    failures: 0/5
```

### Circuit state observability

NATS events `platform.circuit.opened.*` and `platform.circuit.closed.*` are:
1. Written to the mutation ledger as `circuit.opened` / `circuit.closed` events.
2. Published to Mattermost `#platform-security` for `openbao` and `keycloak` circuits (credential infrastructure).
3. Published to Mattermost `#platform-ops` for all other circuits.
4. Tracked in Grafana as a gauge metric: `platform_circuit_state{circuit="keycloak"}` (0=closed, 1=open).

## Consequences

**Positive**

- When Keycloak is restarting, the first 5 failures open the circuit. All subsequent API requests receive an immediate `503` with `Retry-After: 30` instead of waiting 10 seconds each. A 90-second Keycloak restart that would have caused 270+ seconds of cumulative caller wait (30 concurrent requests × 9 seconds average) now causes 150 seconds of circuit-open rejections, reducing total wasted time by 45%.
- Cascading failures are broken at the circuit level. A slow OpenBao (perhaps due to unsealing after a restart) cannot cause every agent workflow to hang simultaneously.
- The distributed circuit state via NATS KV ensures all agents share the same view. Agent A opening a circuit immediately prevents Agent B from attempting the same failing call.

**Negative / Trade-offs**

- Circuit breakers introduce a new failure mode: a circuit that opens too aggressively (low `failure_threshold`) will reject calls that would have succeeded, causing false unavailability. Threshold calibration is critical and must be reviewed after each incident.
- The NATS KV backing for circuit state creates a dependency: if NATS is unavailable, circuit state cannot be read. The circuit breaker falls back to a **local in-memory state** in this case (each process tracks its own circuit independently). This means different agents may have different views of circuit state during a NATS outage, which is acceptable — each agent errs on the side of attempting the call locally.

## Boundaries

- Circuit breakers govern calls made by platform code. They do not govern Ansible SSH connections (those use retry logic directly) or Proxmox VM-level networking.
- The circuit state is advisory for the `soft` degradation policy services. Critical path services (`openbao`, `keycloak`, `nats`) use `hard` policy: an open circuit is a hard error that must be surfaced.

## Related ADRs

- ADR 0058: NATS event bus (JetStream KV for distributed circuit state; nats_outbox for event buffering)
- ADR 0092: Platform API gateway (keycloak circuit wraps JWKS validation)
- ADR 0115: Event-sourced mutation ledger (circuit.opened events)
- ADR 0145: Ollama (fallback when anthropic_api circuit opens)
- ADR 0161: Real-time agent coordination map (circuit state displayed)
- ADR 0163: Retry taxonomy (circuit_open error class → BACKOFF retry; do not retry into an open circuit)
- ADR 0167: Graceful degradation mode declarations (per-circuit OPEN behaviour)
