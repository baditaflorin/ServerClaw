# ADR 0166: Canonical Error Response Format and Error Code Registry

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform exposes errors from multiple surfaces — the API gateway, the goal compiler, the workflow scheduler, NATS event handlers, and Ansible playbook failures — and each currently produces a different error format:

- **API gateway** (`scripts/api_gateway/main.py`): Returns raw HTTP status codes with plain-text bodies for auth failures (`401 Unauthorized`) and upstream errors (`502 Bad Gateway`).
- **Goal compiler**: Raises Python exceptions with string messages. The caller receives an unstructured dict with a `status` key and a human-readable `reason` string.
- **Windmill job failures**: Returns a JSON object with `{"error": {"message": "...", "type": "..."}}` in Windmill's own format.
- **Ansible task failures**: Produces YAML-formatted `FATAL` output with `msg:` key and potentially a `module_stderr:` key.
- **Triage engine**: Returns a custom `TriageReport` dataclass that is serialised differently depending on the caller.
- **Runbook executor**: Returns `{"status": "escalated", "reason": "..."}` with no machine-parseable error code.

An agent that calls multiple platform services must implement a different error parser for each surface. When a new platform service is added (e.g., Gitea ADR 0143, Semaphore ADR 0149), the agent must learn its error format before it can handle failures.

This creates:
- **Code duplication**: Every agent implements ad hoc `if "error" in response else if "FATAL" in output` parsing.
- **Silent error swallowing**: Parsers that don't handle a format return `None` or raise `KeyError`, hiding the original error.
- **Non-machine-parseable errors**: When a goal compiler returns `{"reason": "The target service netbox is currently degraded and safe_to_act is False"}`, an agent cannot programmatically distinguish "health gate failure" from "conflict detected" — both are strings.

The correct fix is a **canonical error response format** with a machine-parseable error code registry, applied uniformly across all platform surfaces that return errors.

## Decision

We will define a **canonical error envelope** and an **error code registry** as the single source of truth for all platform errors. Every platform surface that currently returns an error in a non-canonical format will be migrated.

### Canonical error envelope

```python
# platform/errors/envelope.py

@dataclass
class PlatformError:
    """
    Canonical error response for all platform surfaces.
    Serialises to JSON for HTTP responses; raised as exception in Python code.
    """
    error_code:    str                   # Machine-parseable code (see registry)
    message:       str                   # Human-readable explanation
    trace_id:      str                   # Correlates to ledger/NATS events
    context:       dict        = None    # Structured additional context (not for display)
    retry_advice:  str         = "none"  # "none" | "immediate" | "backoff" | "manual"
    retry_after_s: int | None  = None    # Suggested retry delay (for "backoff")
    docs_url:      str | None  = None    # Link to runbook or ADR
    occurred_at:   str         = field(default_factory=lambda: now().isoformat())

    def to_http_response(self) -> dict:
        return {
            "error": {
                "code":         self.error_code,
                "message":      self.message,
                "trace_id":     self.trace_id,
                "retry_advice": self.retry_advice,
                "retry_after":  self.retry_after_s,
                "docs_url":     self.docs_url,
                "occurred_at":  self.occurred_at,
            }
        }
```

### HTTP response mapping

```python
# HTTP status codes for each error category
ERROR_HTTP_STATUS: dict[str, int] = {
    # Auth / identity
    "AUTH_TOKEN_MISSING":      401,
    "AUTH_TOKEN_EXPIRED":      401,
    "AUTH_TOKEN_INVALID":      401,
    "AUTH_INSUFFICIENT_ROLE":  403,

    # Platform gates
    "GATE_HEALTH_FAIL":        503,   # Health composite gate blocked the intent
    "GATE_CAPABILITY_DENY":    403,   # Agent capability bounds (ADR 0125) denied
    "GATE_CONFLICT":           409,   # Intent conflict (ADR 0127)
    "GATE_BUDGET_EXCEEDED":    429,   # Workflow budget exceeded (ADR 0119)
    "GATE_CIRCUIT_OPEN":       503,   # Circuit breaker open (ADR 0164)
    "GATE_CONCURRENCY_LIMIT":  429,   # Max concurrent instances exceeded

    # Execution
    "EXEC_INTENT_QUEUED":      202,   # Not an error; intent accepted but deferred
    "EXEC_IDEMPOTENT_HIT":     200,   # Not an error; cached result returned
    "EXEC_WORKFLOW_FAILED":    500,   # Workflow ran but failed
    "EXEC_BUDGET_VIOLATION":   500,   # Watchdog killed the workflow
    "EXEC_TIMEOUT":            504,   # Workflow exceeded max_duration_seconds

    # Input validation
    "INPUT_SCHEMA_INVALID":    422,   # Payload fails schema validation
    "INPUT_UNKNOWN_WORKFLOW":  404,   # Workflow ID not in catalog
    "INPUT_UNKNOWN_SERVICE":   404,   # Service ID not in capability catalog

    # Infrastructure
    "INFRA_DEPENDENCY_DOWN":   503,   # Required service unavailable
    "INFRA_LOCK_CONTENTION":   503,   # Resource locked by another agent
    "INFRA_DEADLOCK_DETECTED": 500,   # Deadlock cycle detected (ADR 0162)
}
```

### Error code registry

```yaml
# config/error-codes.yaml — the authoritative registry

error_codes:
  AUTH_TOKEN_MISSING:
    severity: warn
    category: authentication
    retry_advice: none
    description: "No Bearer token in Authorization header"
    docs_url: "https://docs.lv3.org/adr/0056"

  GATE_HEALTH_FAIL:
    severity: info
    category: platform_gate
    retry_advice: backoff
    retry_after_s: 60
    description: "Target service health composite score below safe_to_act threshold"
    docs_url: "https://docs.lv3.org/adr/0128"
    context_fields: [service_id, composite_score, threshold]

  GATE_CIRCUIT_OPEN:
    severity: warn
    category: platform_gate
    retry_advice: backoff
    retry_after_s: null   # Populated from circuit's recovery_window_s at runtime
    description: "Circuit breaker is open for the required dependency"
    docs_url: "https://docs.lv3.org/adr/0164"
    context_fields: [circuit_name, opened_at, recovery_window_s]

  EXEC_WORKFLOW_FAILED:
    severity: error
    category: execution
    retry_advice: manual
    description: "Workflow executed but returned a non-zero exit status"
    docs_url: "https://docs.lv3.org/runbooks/workflow-failure"
    context_fields: [workflow_id, windmill_job_id, exit_code, stderr_snippet]

  INPUT_SCHEMA_INVALID:
    severity: warn
    category: input
    retry_advice: none
    description: "Request payload does not conform to the expected schema"
    docs_url: "https://docs.lv3.org/api-reference"
    context_fields: [field_path, expected_type, received_value]
```

### Migration of existing error surfaces

**API gateway** — all error responses migrated to canonical envelope:

```python
# BEFORE:
raise HTTPException(status_code=401, detail="Invalid token")

# AFTER:
raise PlatformHTTPError(
    PlatformError(
        error_code="AUTH_TOKEN_INVALID",
        message="JWT signature verification failed.",
        trace_id=request.state.trace_id,
        retry_advice="none",
        docs_url="https://docs.lv3.org/adr/0056",
    )
)
```

**Goal compiler** — all `ConflictRejected`, `HealthGateFailed`, etc. exceptions carry a `PlatformError`:

```python
# platform/compiler/goal_compiler.py
raise PlatformError(
    error_code="GATE_HEALTH_FAIL",
    message=f"Service {service_id} composite score {score:.2f} is below threshold {threshold:.2f}.",
    trace_id=ctx.context_id,
    context={"service_id": service_id, "composite_score": score, "threshold": threshold},
    retry_advice="backoff",
    retry_after_s=60,
)
```

**Platform CLI** — maps error codes to actionable operator messages:

```python
# platform/cli/error_handler.py
ERROR_MESSAGES = {
    "GATE_HEALTH_FAIL": "⚠ Service is currently unhealthy. The platform will retry automatically.",
    "GATE_CIRCUIT_OPEN": "⚠ Dependency {circuit_name} is down. Retry in {recovery_window_s}s.",
    "EXEC_WORKFLOW_FAILED": "✗ Workflow failed. See job {windmill_job_id} for details.",
    "AUTH_TOKEN_EXPIRED": "✗ Session expired. Run `lv3 auth login` to renew.",
}
```

### Agent error handling

Agents use error codes for programmatic branching:

```python
try:
    result = platform_api.run_intent(intent)
except PlatformError as e:
    match e.error_code:
        case "GATE_HEALTH_FAIL" | "GATE_CIRCUIT_OPEN" | "INFRA_LOCK_CONTENTION":
            # Backoff and retry; platform will recover
            intent_queue.enqueue(intent, delay=e.retry_after_s or 60)
        case "GATE_CAPABILITY_DENY":
            # Escalate to higher-trust agent or operator
            handoff.escalate(task, reason=e.message)
        case "INPUT_SCHEMA_INVALID":
            # Bug in the agent's parameter construction; do not retry
            ledger.write("agent.error", {"code": e.error_code, "context": e.context})
            raise AgentBug(e.message)
        case "EXEC_WORKFLOW_FAILED":
            # Workflow-level failure; triage engine should investigate
            triage.submit_signal(service_id=intent.target, error_code=e.error_code)
```

## Consequences

**Positive**

- All agent error handling collapses to a single `match e.error_code` branch. Adding a new platform service (e.g., Gitea, Semaphore) does not require agents to learn a new error format.
- The `retry_advice` and `retry_after_s` fields on every error eliminate the need for agents to infer retry behaviour from HTTP status codes or error message strings.
- The error code registry (`config/error-codes.yaml`) is a single authoritative source that can be rendered into the developer portal (ADR 0094) as a complete error reference, reducing operator debugging time.

**Negative / Trade-offs**

- Migrating all existing error surfaces requires touching the API gateway, goal compiler, triage engine, runbook executor, and CLI. This is a significant one-time migration effort that must be carefully tested to avoid regressions.
- `message` is human-readable and may change between platform versions as descriptions are improved. Agents must never parse `message` programmatically — only `error_code` is stable. This discipline must be enforced by code review.

## Boundaries

- Canonical errors apply to the platform's own API surfaces. Ansible task failure output, Windmill job logs, and Docker container stderr are not normalised — they are raw diagnostic data, not platform API responses.
- The error code registry is append-only; existing codes are never removed or changed in meaning (only deprecated with a `deprecated_since` field).

## Related ADRs

- ADR 0031: Repository validation pipeline (error-codes.yaml validated in pipeline)
- ADR 0090: Platform CLI (error_handler.py maps codes to operator messages)
- ADR 0092: Platform API gateway (first surface to adopt canonical envelope)
- ADR 0112: Deterministic goal compiler (compiler errors use canonical codes)
- ADR 0163: Retry taxonomy (retry_advice field aligns with TRANSIENT/BACKOFF/PERMANENT classes)
- ADR 0164: Circuit breaker (GATE_CIRCUIT_OPEN error code)
