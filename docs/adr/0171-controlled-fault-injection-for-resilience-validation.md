# ADR 0171: Controlled Fault Injection for Resilience Validation

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

ADRs 0163–0170 define a comprehensive set of resilience mechanisms: retry policies, circuit breakers, idempotency keys, error formats, degradation modes, idempotent Ansible roles, structured logging, and timeout hierarchies. These mechanisms are designed to make the platform stable under failure conditions.

However, **designed resilience is not the same as verified resilience**. There is no current mechanism to verify that:

- The circuit breaker for Keycloak actually opens after 5 consecutive failures (and not silently absorb them or open after 3 or 10).
- The secret cache actually serves stale values when OpenBao is unavailable (and does not panic or return an empty string).
- The NATS outbox actually buffers events when NATS is down (and not drop them silently).
- The idempotency key deduplication actually prevents a double-rotation when two concurrent submissions arrive.
- The deadlock detector actually resolves a deadlock within 30 seconds (and not leave agents blocked for 10 minutes).
- The Ansible role for `nginx_edge_publication` is still idempotent after the latest nginx version upgrade.

Without periodic verification, resilience mechanisms **decay**: a code change that inadvertently breaks the circuit breaker logic will go undetected until the next real Keycloak outage. By the time the real failure happens, operators may have forgotten that the circuit breaker was even there.

**Fault injection** (a form of controlled chaos engineering) addresses this by **deliberately inducing failures** in a controlled, scripted way, verifying that the system behaves as declared, and alerting when it does not.

The scope is deliberately narrow: a single-node homelab is not the place for large-scale distributed chaos experiments. Fault injection here targets specific, declared resilience mechanisms (ADR 0167 degradation modes) and verifies them with precise assertions.

## Decision

We will implement a **controlled fault injection suite** as a monthly Windmill workflow `run-fault-injection` that verifies each declared resilience mechanism against its expected behaviour.

### Fault injection framework

```python
# platform/faults/injector.py

@dataclass
class FaultScenario:
    name: str
    description: str
    fault_type: str        # "service_kill" | "port_block" | "slow_response" | "disk_fill" | "error_response"
    target: str            # Service or resource being faulted
    duration_s: int        # How long the fault is applied
    expected_behaviour: str  # What the platform should do during the fault
    recovery_expected: bool  # Should the platform auto-recover?
    assertion: Callable    # Function that validates the expected behaviour

class FaultInjector:

    def run_scenario(self, scenario: FaultScenario) -> FaultResult:
        """Apply a fault, verify behaviour, and restore the system."""
        pre_state = self._capture_platform_state()
        fault_token = None
        try:
            # Apply the fault
            fault_token = self._apply_fault(scenario)
            # Wait for the platform to detect and respond
            time.sleep(scenario.duration_s)
            # Run the assertion
            result = scenario.assertion(scenario, pre_state)
            return FaultResult(scenario=scenario, passed=result.passed, details=result)
        finally:
            # Always remove the fault, even if assertion fails
            if fault_token:
                self._remove_fault(fault_token)
            self._wait_for_recovery(scenario, timeout_s=120)
            post_state = self._capture_platform_state()
            self._assert_full_recovery(pre_state, post_state)
```

### Fault types

**`service_kill`**: Stop a Docker container temporarily using `docker stop <container>`.

```python
def apply_service_kill(target: str) -> FaultToken:
    container_id = docker.get_container_id(target)
    docker.stop(container_id, timeout=0)
    return FaultToken(type="service_kill", container_id=container_id)

def remove_service_kill(token: FaultToken):
    docker.start(token.container_id)
```

**`slow_response`**: Use `tc` (traffic control) on the VM's loopback or internal bridge to add latency:

```python
def apply_slow_response(target_port: int, delay_ms: int) -> FaultToken:
    # Adds artificial 2000ms latency to a specific port using Linux tc
    run_ssh(f"tc qdisc add dev lo root handle 1: prio && "
            f"tc qdisc add dev lo parent 1:3 handle 30: netem delay {delay_ms}ms && "
            f"tc filter add dev lo protocol ip parent 1:0 prio 3 u32 match ip dport {target_port} 0xffff flowid 1:3")
    return FaultToken(type="slow_response", port=target_port)
```

**`error_response`**: Inject a temporary nginx `return 503` for a specific upstream using a location block override.

### Declared fault scenarios

Each scenario maps to a degradation mode declaration (ADR 0167):

```yaml
# config/fault-scenarios.yaml

scenarios:

  - name: fault:keycloak-unavailable
    description: "Kill Keycloak container for 45 seconds; verify circuit opens and API gateway degrades gracefully"
    fault_type: service_kill
    target: keycloak
    duration_s: 45
    expected_behaviour: |
      After 5 failures (≤25s), circuit opens. API gateway returns 503 + Retry-After:30.
      JWKS cached values serve auth for up to 300s.
    assertion: assert_keycloak_circuit_behaviour

  - name: fault:openbao-unavailable
    description: "Add 6000ms latency to OpenBao port; verify secret cache serves stale values"
    fault_type: slow_response
    target_port: 8200
    duration_s: 60
    expected_behaviour: |
      OpenBao requests time out after 5s (circuit policy). After 3 timeouts, circuit opens.
      CachedSecretClient returns cached values. No workflow fails due to missing secret.
    assertion: assert_openbao_degradation

  - name: fault:nats-unavailable
    description: "Kill NATS container for 30 seconds; verify outbox buffers all events"
    fault_type: service_kill
    target: nats
    duration_s: 30
    expected_behaviour: |
      NATS publish calls fail. ResilientNATSPublisher writes to platform.nats_outbox.
      After NATS recovers, outbox is flushed within 10 seconds.
      Zero events are lost.
    assertion: assert_nats_outbox_behaviour

  - name: fault:postgres-unavailable
    description: "Kill Postgres container for 20 seconds; verify Windmill fails hard, platform API queues"
    fault_type: service_kill
    target: postgresql
    duration_s: 20
    expected_behaviour: |
      Windmill API returns 500 (hard dependency).
      Platform API queues incoming intents (soft dependency).
      After Postgres recovers, queued intents are dispatched within 60 seconds.
    assertion: assert_postgres_degradation

  - name: fault:deadlock-injection
    description: "Create an artificial agent deadlock via crafted lock acquisitions; verify detector resolves within 60s"
    fault_type: programmatic      # Directly manipulates lock registry (ADR 0153)
    duration_s: 90
    expected_behaviour: |
      Deadlock detector identifies cycle within 60 seconds.
      Lowest-priority lock holder is aborted.
      Remaining agent proceeds. System returns to normal within 90 seconds.
    assertion: assert_deadlock_resolution

  - name: fault:slow-ansible
    description: "Inject sleep into an Ansible task via a test role; verify timeout hierarchy enforces the limit"
    fault_type: programmatic
    duration_s: 180
    expected_behaviour: |
      Ansible task is killed by async timeout after ansible_task_timeout_s (120s).
      Workflow budget watchdog receives 'ansible_timeout' signal.
      Workflow is marked 'timeout' in ledger. No zombie processes remain.
    assertion: assert_ansible_task_timeout
```

### Assertion functions

Each assertion verifies the declared behaviour programmatically:

```python
def assert_keycloak_circuit_behaviour(scenario: FaultScenario, pre_state: PlatformState) -> AssertionResult:
    # Assert circuit opened
    circuit_state = circuit_registry.get("keycloak")
    if circuit_state.state != "open":
        return AssertionResult(passed=False, reason=f"Circuit is {circuit_state.state}, expected 'open'")

    # Assert API gateway returns 503, not a timeout
    start = time.time()
    resp = requests.get("https://api.lv3.org/v1/platform/health", headers={"Authorization": "Bearer invalid"})
    latency = time.time() - start
    if resp.status_code != 503:
        return AssertionResult(passed=False, reason=f"Expected 503, got {resp.status_code}")
    if latency > 1.0:
        return AssertionResult(passed=False, reason=f"Circuit-open response too slow: {latency:.2f}s (expected <1s)")

    return AssertionResult(passed=True)
```

### Schedule and reporting

The fault injection suite runs:
- **Monthly** (first Sunday, 03:00 UTC, maintenance window).
- **After each major deployment** (`make apply-all`): a subset of the most critical scenarios (keycloak, openbao, nats) is run to verify the newly deployed code still honours all degradation modes.
- **On demand**: `lv3 run fault-injection --scenario fault:keycloak-unavailable`.

Results are posted to Mattermost `#platform-resilience` and written to the mutation ledger:

```
📊 Monthly fault injection run: 2026-03-24 03:00 UTC

✓ fault:keycloak-unavailable     Circuit opened in 22s. API degraded correctly. Recovery: 34s.
✓ fault:openbao-unavailable      Cache served 3 requests during outage. Zero workflow failures.
✓ fault:nats-unavailable         12 events buffered. 11 flushed on recovery (1 expired: TTL<30s ⚠)
✓ fault:postgres-unavailable     Windmill failed hard. 3 intents queued. All dispatched after recovery.
✓ fault:deadlock-injection       Deadlock detected in 28s. Lower-priority agent aborted. System clean.
✗ fault:slow-ansible             Ansible task NOT killed at 120s (still running at 145s). BUG FOUND.

5/6 passed. 1 failure. Created GlitchTip issue #312: ansible_task_timeout not enforced.
```

A failure in the fault injection suite creates a GlitchTip incident (ADR 0061) with `MEDIUM` severity and triggers the triage engine.

## Consequences

**Positive**

- Resilience mechanisms are verified empirically, not just by design intent. The monthly run catches regressions before they manifest in production: if a code change breaks circuit breaker logic, the fault injection run discovers it at 03:00 on the first Sunday of the month, not during the next real Keycloak outage.
- The post-deployment subset run means that any deployment that breaks a resilience mechanism is caught immediately, before the operator closes their laptop for the day.
- The fault scenarios are documentation of expected behaviour, not just tests. An operator reading `config/fault-scenarios.yaml` understands exactly what the platform does during each failure mode.

**Negative / Trade-offs**

- Fault injection runs on the production system (there is no separate staging environment). The scenarios are designed to be safe — each fault is bounded in duration, the injector always removes the fault in a `finally` block, and recovery is verified before the run completes. But a bug in the fault injector itself (e.g., a fault that is not removed) could cause real service degradation. The scenarios that kill Docker containers are particularly risky.
- The monthly schedule means a resilience regression can persist for up to 30 days before being detected. The post-deployment subset run mitigates this for regressions introduced by deployments, but not for regressions introduced by external changes (upstream library updates, OS patches).

## Boundaries

- Fault injection targets platform-layer services (Docker containers, NATS, Postgres). It does not target the Proxmox host, physical hardware, or external services.
- The `programmatic` fault type manipulates internal platform state (lock registry, Postgres tables). It is limited to controlled test scenarios and cannot be triggered remotely (requires `platform-admin` role).

## Related ADRs

- ADR 0061: GlitchTip (fault injection failures create incidents)
- ADR 0143: Gitea CI (post-deployment fault injection subset)
- ADR 0153: Distributed resource lock registry (deadlock injection scenario)
- ADR 0162: Deadlock detection (verified by fault:deadlock-injection)
- ADR 0163: Retry taxonomy (retry behaviour verified under fault conditions)
- ADR 0164: Circuit breaker (circuit opening and closing verified by fault:*-unavailable)
- ADR 0167: Graceful degradation modes (each scenario directly validates a declared degradation mode)
- ADR 0170: Timeout hierarchy (verified by fault:slow-ansible)
