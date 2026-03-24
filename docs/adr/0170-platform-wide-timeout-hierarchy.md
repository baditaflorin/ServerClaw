# ADR 0170: Platform-Wide Timeout Hierarchy

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform has timeouts at several layers, but they are not coordinated:

- **API gateway**: `timeout_seconds: 15` per upstream service (in `config/api-gateway-catalog.json`).
- **Windmill workflow budget**: `max_duration_seconds: 600` (default).
- **SSH connections** (drift_lib.py): `ConnectTimeout: 10`.
- **JWKS fetch** (api_gateway): `timeout=10`.
- **NetBox inventory sync**: `max_attempts=5` with `retry_delay_seconds=2` — no explicit total timeout.
- **Watchdog poll interval**: 30 seconds (checks for budget violations).

The problem is that **outer operations have longer timeouts than inner operations they depend on**, which is the correct pattern — but this is only accidental, not enforced. The real failure mode is the inverse: an outer timeout that expires before the inner operation has a chance to complete.

**Concrete scenario:** The API gateway has a 15-second timeout for proxied requests. A Grafana query that takes 20 seconds (legitimate, for a complex dashboard) times out at the gateway, even though Grafana itself would have returned a successful response at 20 seconds. The timeout is too tight for the operation it is guarding.

**Inverse scenario (worse):** A Windmill job that runs an Ansible playbook has `max_duration_seconds: 600`. The playbook runs an `apt install` task that has no timeout configured. The `apt` process hangs waiting for a locked package database. The watchdog polls every 30 seconds and would detect the violation after 600 seconds — but the watchdog check itself waits for the Windmill job to respond to a status query, which can hang if Windmill is busy. The result: the job hangs indefinitely because the outer timeout is never enforced.

The correct model is a **timeout hierarchy**: every operation at every layer has an explicit timeout, and outer timeouts are always longer than the sum of inner timeouts. This is called a **deadline propagation** model — the outer deadline is passed inward, and inner operations respect the remaining time budget.

## Decision

We will define a **platform-wide timeout hierarchy** in `config/timeout-hierarchy.yaml` and enforce it through a combination of code conventions and automated validation.

### Timeout hierarchy

```yaml
# config/timeout-hierarchy.yaml
# All times in seconds. Outer contexts must always exceed their inner children.

layers:
  - layer: operator_session         # Human or agent session (ADR 0123)
    timeout_s: 3600                 # 1 hour; operator can always run a new session
    inner_layers: [workflow_execution]

  - layer: workflow_execution       # Full Windmill workflow run
    timeout_s: 600                  # 10 minutes; replaces max_duration_seconds default
    inner_layers: [ansible_play, api_call_chain, script_execution]

  - layer: ansible_play             # Full ansible-playbook run
    timeout_s: 480                  # 8 minutes; leaves 2 minutes for pre/post steps
    inner_layers: [ansible_task, ssh_connection]

  - layer: ansible_task             # Single Ansible task
    timeout_s: 120                  # 2 minutes per task
    inner_layers: [ssh_connection, http_request, subprocess]

  - layer: ssh_connection           # SSH connect + command
    timeout_s: 30                   # 30-second connection establishment
    inner_layers: [subprocess]

  - layer: subprocess               # Shell command or script
    timeout_s: 60                   # 1 minute for any subprocess
    inner_layers: []

  - layer: api_call_chain           # Multi-step API call sequence
    timeout_s: 60                   # Entire chain
    inner_layers: [http_request]

  - layer: http_request             # Single HTTP request
    timeout_s: 30                   # Connect + transfer; replaces inconsistent values
    inner_layers: []

  - layer: script_execution         # Python platform script
    timeout_s: 300                  # 5 minutes for a standalone script
    inner_layers: [http_request, subprocess]

  - layer: health_probe             # Single health probe check
    timeout_s: 5                    # Short; probes must be fast
    inner_layers: []

  - layer: liveness_probe           # Minimal liveness check
    timeout_s: 2                    # Very short; liveness must never block
    inner_layers: []
```

**Hierarchy validation rule**: for every layer with `inner_layers`, `timeout_s > sum(child.timeout_s) for all children`. A validation script (`scripts/validate_timeout_hierarchy.py`) checks this and fails the build if violated.

### Deadline propagation

The key insight of deadline propagation: when an outer operation starts with a `timeout_s=600` budget, it passes the **remaining deadline** to inner operations. Inner operations must not run longer than the remaining time.

```python
# platform/timeouts/context.py

class TimeoutContext:
    """
    A propagating deadline context. Passed through all platform call chains.
    Inner operations check remaining time before starting.
    """
    def __init__(self, total_seconds: float, layer: str):
        self.deadline = time.monotonic() + total_seconds
        self.layer = layer

    def remaining(self) -> float:
        """Seconds remaining before deadline."""
        return max(0.0, self.deadline - time.monotonic())

    def sub_context(self, layer: str, max_seconds: float) -> "TimeoutContext":
        """
        Create a child context with the minimum of the given budget and
        the remaining parent deadline. This is the key: the child cannot
        exceed the parent's remaining time.
        """
        available = self.remaining()
        child_budget = min(max_seconds, available * 0.9)  # 10% buffer for overhead
        if child_budget < 1.0:
            raise TimeoutExceeded(
                f"Insufficient time for {layer}: {available:.1f}s remaining, need ≥1s"
            )
        return TimeoutContext(child_budget, layer)

    def __enter__(self):
        if self.remaining() <= 0:
            raise TimeoutExceeded(f"Deadline already exceeded at layer {self.layer}")
        return self

    def __exit__(self, *args):
        pass  # No action; caller checks remaining() for subsequent operations
```

### HTTP request timeout enforcement

All HTTP clients in the platform use a request-level timeout derived from the current timeout context:

```python
# platform/http/client.py

def get(url: str, timeout_ctx: TimeoutContext, **kwargs) -> requests.Response:
    """
    HTTP GET with timeout derived from the current timeout context.
    Never uses a hardcoded timeout value.
    """
    layer_limit = TIMEOUT_HIERARCHY["http_request"]["timeout_s"]
    actual_timeout = min(layer_limit, timeout_ctx.remaining() - 1.0)
    if actual_timeout < 0.5:
        raise TimeoutExceeded("Insufficient time for HTTP request")
    return requests.get(url, timeout=actual_timeout, **kwargs)
```

This replaces the current pattern of hardcoded `timeout=10`, `timeout=15`, `timeout=30` throughout the codebase.

### Ansible timeout enforcement

Ansible tasks that can hang are given explicit timeouts via `async:` and `poll:`:

```yaml
# In Ansible tasks that can hang (apt, dnf, long-running commands)
- name: Install packages
  ansible.builtin.apt:
    name: "{{ packages }}"
    state: present
  async: "{{ ansible_task_timeout_s | default(120) }}"  # From timeout hierarchy
  poll: 5
  register: apt_job

- name: Wait for package installation
  ansible.builtin.async_status:
    jid: "{{ apt_job.ansible_job_id }}"
  register: apt_result
  until: apt_result.finished
  retries: "{{ (ansible_task_timeout_s | default(120) / 5) | int }}"
  delay: 5
```

The `ansible_task_timeout_s` variable is injected by the playbook runner from the current timeout context.

### Watchdog enhancement

The existing watchdog (ADR 0119) polls every 30 seconds. With the timeout hierarchy enforced at the code level, the watchdog becomes a **backstop** rather than the primary enforcement mechanism. Its poll interval is reduced to 10 seconds to catch budget violations faster:

```python
# platform/scheduler/watchdog.py (updated)
POLL_INTERVAL_SECONDS = 10  # Reduced from 30; hierarchy enforces most timeouts at code level
```

### Timeout hierarchy violations as CI failures

```yaml
# .gitea/workflows/validate.yml — extended with timeout hierarchy check
- name: Validate timeout hierarchy
  run: python3 scripts/validate_timeout_hierarchy.py config/timeout-hierarchy.yaml

- name: Check for hardcoded timeouts in Python code
  run: |
    python3 scripts/ci/check_hardcoded_timeouts.py \
      --disallow "timeout=[0-9]" \
      --allow "timeout=timeout_ctx.remaining()" \
      --paths platform/ scripts/
```

The `check_hardcoded_timeouts.py` script flags any `timeout=<literal>` in Python code outside of `config/timeout-hierarchy.yaml` references, requiring all timeouts to be derived from the hierarchy.

## Consequences

**Positive**

- The "hung forever" failure mode is eliminated by design. Every operation at every layer has an explicit timeout, and that timeout is shorter than its parent's remaining deadline. An operation that hangs will be terminated by its own timeout, not by the outer watchdog.
- The API gateway's per-service timeout is derived from the hierarchy rather than hardcoded. Services that legitimately need more time (e.g., a Grafana dashboard export) can increase their `http_request` budget at the service level without requiring a code change.
- The 10% overhead buffer in `sub_context()` prevents the "I have 1 second left and I just started an HTTP request" scenario where every layer consumes its full budget and the outermost layer times out exactly at the right moment.

**Negative / Trade-offs**

- Deadline propagation requires threading the `TimeoutContext` through every function call that performs I/O. This is a significant refactoring effort for existing code. The migration can be phased: start with the critical path (API gateway → goal compiler → Windmill submission) and extend outward.
- The hierarchy validation rule (`outer > sum(children)`) is a conservative constraint. In practice, most inner operations complete well within their budget, so the outer operation's full timeout is never consumed. The hierarchy protects against the pathological case where every inner operation consumes its maximum budget simultaneously.

## Boundaries

- The timeout hierarchy governs platform code. Windmill's internal job timeout (`max_duration_seconds`) must be set to match the `workflow_execution` layer timeout. Third-party app request timeouts (Grafana, NetBox) are not governed by this ADR.
- `async:` / `poll:` is used for Ansible tasks that can hang. For tasks that are expected to be fast (file operations, variable assertions), no explicit timeout is needed.

## Related ADRs

- ADR 0064: Health probe contracts (health_probe and liveness_probe layer timeouts)
- ADR 0092: Platform API gateway (http_request timeout replaces per-service hardcoded values)
- ADR 0119: Budgeted workflow scheduler (workflow_execution timeout aligns with hierarchy)
- ADR 0143: Gitea CI (hierarchy validation in CI)
- ADR 0163: Retry taxonomy (timeout errors → BACKOFF class; hierarchy prevents indefinite hangs)
- ADR 0172: Watchdog escalation (watchdog reduced to backstop role; hierarchy is primary enforcement)
