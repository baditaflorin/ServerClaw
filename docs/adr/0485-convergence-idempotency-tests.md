# ADR 0485: Convergence Idempotency Tests

**Status**: ACCEPTED
**Date**: 2026-05-12
**Decision**: Every state-changing target (`make converge-*`, `make provision-guests`, `make live-apply-*`, `make bootstrap`) is required to be **idempotent in the strict sense**: running it twice against an already-converged deployment performs zero changes and produces zero side-effects. Idempotency is verified by an automated test, not a hope.

---

## Context

### Ansible's `changed_when` is not idempotency

Ansible reports a "changed" count per task, which operators use as a hint. But:

- A task can be `changed: 0` while having genuinely mutated state (e.g. `shell:` tasks without `creates:` always report `changed`, but a wrapper using `changed_when: false` reports clean even when it shouldn't).
- A task can be `changed: 1` on every run despite producing the same end-state (e.g. `template:` modules that render slightly different output each time from non-deterministic inputs).
- A converge can be "OK" on first run but mutate further state on second run (e.g. a role that increments a counter, or generates a random secret if absent and stores it).

The platform has none of these failure modes today *that we know of*. The point of this ADR is to make absence-of-knowledge into presence-of-evidence.

### Why this matters for hands-off bootstrap (ADR 0483)

Hands-off bootstrap is built on resumable steps. Resumability requires that re-running a step that already succeeded is **safe**. If converge-keycloak rotates a secret on every run, then a bootstrap that fails at step 11 and resumes from step 10 silently invalidates keycloak's secrets for every downstream service. The chain breaks invisibly.

Resumability also requires that re-running a step that *partially* succeeded converges to the same end-state as a fresh run. Otherwise, "resume" is a different operation than "run from scratch" — and the operator (or agent) has to know which mode they're in.

Strict idempotency removes this distinction: every step is **safe to re-run**, every run produces the same end-state, and every run after the first produces zero changes.

### Why this matters for drift detection

If running `make converge-X` against a clean deployment produces zero changes, then any *non-zero* change count on a re-run is a drift signal: something between the converges modified the state. The drift detector becomes "run converge in check-mode, count non-zero changes" — which is the simplest possible signal.

---

## Decision

### 1. Two-run convergence test

Every converge target gets a corresponding `make idempotency-test-<target>` (or rolled up under `make idempotency-test-all`). The test:

```python
# tests/integration/test_idempotency.py (concept)
def test_target_is_idempotent(target):
    # Run 1: real converge.
    result1 = run(f"make {target}")
    assert result1.exit_code == 0
    record1 = parse_ansible_play_recap(result1)

    # Run 2: same target, immediately.
    result2 = run(f"make {target}")
    assert result2.exit_code == 0
    record2 = parse_ansible_play_recap(result2)

    # Assertions:
    assert record2.changed == 0, f"second run made changes: {record2.diff}"
    assert record2.failed == 0
    assert record2.unreachable == 0
```

The test is **not** a unit test. It runs against a real (preferably ephemeral) Proxmox host. CI runs it against a tiny fixture deployment; pre-push gate skips it (too slow) but a nightly job runs the full suite.

### 2. Idempotency receipt

Each successful idempotency test writes a receipt:

```
receipts/idempotency/<target>/<YYYY-MM-DD>.json
```

Containing:

```json
{
  "target": "converge-harbor",
  "ran_at": "2026-05-12T03:00:00Z",
  "fixture_deployment": "ci-ephemeral-001",
  "run1": {"changed": 14, "duration_s": 312},
  "run2": {"changed": 0, "duration_s": 41},
  "idempotent": true
}
```

A target that fails idempotency for one run is **not** allowed back into the main converge set without a remediation receipt explaining the change.

### 3. The reverse-direction test: detect-drift

If two consecutive converges produce identical state, then any external modification between converges is detectable:

```bash
make detect-drift target=converge-harbor
# Effectively: run in --check mode; if any task would change, drift exists.
```

`detect-drift` is the read-only sibling of `converge`. The drift signal feeds into `make doctor` (ADR 0450). When `detect-drift` reports drift, `make doctor-strict` exits non-zero — that's the alerting hook.

### 4. Five common idempotency violations to lint for

The pre-push gate (or a pre-merge CI check) refuses any new role that contains these anti-patterns:

| Anti-pattern | Why it breaks idempotency | Lint rule |
|---|---|---|
| `shell:` without `creates:`, `removes:`, or explicit `changed_when` | Always reports `changed` | grep + AST check on roles |
| `command:` invoking a clock-dependent or random-output command | Non-deterministic | Heuristic: warn on `date`, `uuidgen`, `openssl rand` etc. without explicit `changed_when: false` |
| `template:` with `mode:` differing from previous render | Forces a change every run | Lint: enforce explicit `mode:` |
| `lineinfile` without `regexp:` | Appends on every run | Lint: warn on absence |
| `copy:` of locally-generated secrets that are regenerated each invocation | New secret bytes every run | Audit list of secret-emitting roles; require `creates:` clause or a stable secret store reference |

### 5. The "no random-on-each-run" rule for secrets

If a role generates a secret (Keycloak client secret, OpenBao root token, etc.), it does so **once** per deployment, stores the result idempotently (in OpenBao or `.local/<service>/`), and reads-or-creates on subsequent runs. The lint enforces this: any role with `openssl rand` or `lookup('password', …)` must be paired with a `stat:` check that reads the existing secret if present.

This is the rule that, if violated, breaks resumability hardest. Every role currently shipping secrets must be audited (tracked in ws-0485-secret-idempotency-audit).

### 6. The fixture deployment

Idempotency tests need a target. The "real" deployments (lv3, 0fork) are too slow / risky to use for nightly idempotency runs. A dedicated fixture:

```
.local/deployments/ci-ephemeral-001/
```

is provisioned-then-torn-down by the CI runner. The provisioning uses the same `make bootstrap` chain as a real deployment, but against a tiny Proxmox-in-Docker (or Proxmox-on-a-disposable-VM) — fast cycle, real Ansible execution.

This fixture is defined in `config/contracts/deployment-v1/fixture-deployments.yml` and built by `make fixture-up` (which already exists per the Makefile recon in ws-0481).

### 7. Out of scope

- **Test-driven role development.** This ADR specifies *idempotency* testing. Functional/role-level testing (Molecule, etc.) is a separate ADR.
- **Performance regression detection.** Comparing run1/run2 durations could surface "this role suddenly takes 10× longer." Useful but separate.
- **Crashed-mid-converge recovery testing.** "Run converge, kill it after 60s, re-run" is a richer test than this ADR specifies. Future work.

---

## Consequences

### Positive

- **Hands-off bootstrap becomes safe.** Resumability is guaranteed by construction: every step is safe to re-run.
- **Drift detection is one line.** `detect-drift` invokes converge in --check mode; non-zero changes = drift.
- **Lint catches the easy mistakes before merge.** The five anti-patterns above are the common sources of "works fine, mysteriously regresses next week."
- **The fixture deployment becomes a CI asset that exercises real Ansible.** Today, role tests are largely syntax checks; idempotency tests are state-machine checks.

### Negative

- **Nightly CI cost.** Spinning up a fixture deployment and running every converge twice is minutes-to-hours of compute per night. Acceptable for the value.
- **Existing roles need audit.** Some currently violate idempotency in small ways (e.g. printing the current date into a config comment). Each violation needs a fix or a documented exception. Tracked in ws-0485.
- **The lint will produce false positives initially.** A `shell:` with a side effect that's truly idempotent ("docker stop X") will get flagged; explicit `changed_when: false` is the contract documenting "yes I know."

### Migration

1. This PR: ADR + lint stubs + initial test harness.
2. ws-0485 task list: audit every role for the five anti-patterns; fix or document.
3. CI gets a nightly job running `make idempotency-test-all`.
4. Pre-push gets the lint (advisory at first, blocking after a grace period).

---

## References

- ADR 0420 — Receipt schema
- ADR 0450 — Drift signals + `make doctor`
- ADR 0481 — Explicit deployment context
- ADR 0482 — Capacity-aware dynamic sizing
- ADR 0483 — Hands-off bootstrap (the consumer)
- ADR 0484 — Self-verification contracts (the sibling)
