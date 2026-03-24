# ADR 0129: Runbook Automation Executor

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform has a growing library of runbooks in `docs/runbooks/*.md` that describe step-by-step remediation and operational procedures. These runbooks are searchable (ADR 0121) and surfaced by the triage engine (ADR 0114) as remediation guidance. However, every runbook step is executed manually: an operator reads the runbook, interprets each step, and runs the appropriate commands.

The consequence is that well-understood, fully-scripted failure modes — certificate renewal, service restart, connection pool drain and restore, backup verification — require operator involvement for execution even when every step is deterministic and idempotent. An operator following a runbook mechanically is doing work that could be done by the platform.

The observation-to-action closure loop (ADR 0126) connects findings to intent compilation and execution, but it targets single-workflow intents. Multi-step runbook execution — where step N's output informs step N+1's input, and failure at step N requires a fallback path — is outside the closure loop's scope.

The triage engine selects runbooks by search, but once selected, the runbook sits in Mattermost as text for an operator to execute. The case library (ADR 0118) stores remediation steps from resolved incidents, but those steps are not executable.

We need a runbook automation executor that can:
1. Parse a structured runbook into discrete executable steps.
2. Execute each step as a platform workflow intent.
3. Verify the success condition after each step before proceeding.
4. Branch on step failure: try fallback steps, escalate to an operator, or open a new incident.
5. Write a complete execution trace to the ledger and update the case library on success.

## Decision

We will implement a **runbook automation executor** as a Windmill workflow that accepts a runbook identifier and an execution context, then drives each step through the goal compiler (ADR 0112) and scheduler (ADR 0119) with explicit verification between steps.

### Runbook step schema

Runbooks are authored as Markdown with a structured YAML front matter block that defines the automation-compatible steps. Prose-only runbooks (without automation front matter) remain human-readable and are not subject to this ADR.

```yaml
# docs/runbooks/renew-tls-certificate.md front matter

---
id: renew-tls-certificate
title: Renew an expiring TLS certificate
automation:
  eligible: true
  agent_trust_required: T2           # Minimum agent trust tier (ADR 0125)

steps:
  - id: check-expiry
    type: diagnostic
    description: Confirm the certificate is expiring within 14 days
    workflow_id: check-cert-expiry
    params:
      service: "{{ service }}"
    success_condition: "result.days_remaining <= 14"
    on_failure: escalate             # If cert is not actually expiring, stop and escalate

  - id: renew-cert
    type: mutation
    description: Request renewal from step-ca
    workflow_id: renew-service-cert
    params:
      service: "{{ service }}"
    success_condition: "result.new_expiry_days >= 90"
    on_failure: escalate

  - id: verify-health
    type: diagnostic
    description: Confirm service health probe passes after renewal
    workflow_id: check-service-health
    params:
      service: "{{ service }}"
    wait_seconds: 15
    success_condition: "result.status == 'healthy'"
    on_failure: retry_once           # Retry once before escalating

  - id: update-case
    type: system
    description: Record successful renewal in case library
    workflow_id: update-case-library
    params:
      case_category: certificate_expiry
      service: "{{ service }}"
      resolution: "Certificate renewed. New expiry: {{ steps.renew-cert.result.new_expiry_days }} days."
    success_condition: null          # Fire-and-forget
---
```

### Execution model

The executor runs steps sequentially. Each step is:

1. Compiled into an `ExecutionIntent` via the goal compiler.
2. Checked against the health composite index (ADR 0128): if `safe_to_act` is False, the step is held.
3. Checked for conflicts (ADR 0127): if a conflict is detected, the step is held until the blocking intent clears.
4. Submitted to the budgeted scheduler (ADR 0119).
5. Verified against the step's `success_condition` after completion.
6. The result is stored in `steps.<step_id>.result` and available to subsequent steps via template substitution.

```python
# platform/runbook/executor.py

class RunbookExecutor:
    def execute(self, runbook_id: str, params: dict, actor_id: str) -> RunbookRun:
        run = RunbookRun.create(runbook_id, params, actor_id)
        ctx = BootstrapClient().hydrate(actor_id=actor_id)

        for step in runbook.steps:
            result = self._execute_step(step, run, ctx)
            if result.status == "failed":
                action = self._handle_failure(step, result, run)
                if action == "escalate":
                    run.escalate(step, result)
                    return run        # Pause; await operator
                elif action == "retry_once":
                    result = self._execute_step(step, run, ctx)  # One retry
                    if result.status == "failed":
                        run.escalate(step, result)
                        return run
            run.record_step(step, result)

        run.complete()
        return run
```

### Failure strategies

| Strategy | Behaviour |
|---|---|
| `escalate` | Stop execution, write ledger event, post to Mattermost, await operator input |
| `retry_once` | Re-execute the step once; if it fails again, escalate |
| `skip` | Skip the step and proceed to the next (only allowed on `type: diagnostic` steps) |
| `rollback` | Execute the runbook's declared `rollback_workflow_id` and then escalate |
| `continue` | Record the failure as a warning and proceed to the next step |

### Run record

```sql
CREATE TABLE runbook.runs (
    run_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    runbook_id     TEXT NOT NULL,
    actor_id       TEXT NOT NULL,
    context_id     UUID,
    params         JSONB NOT NULL,
    status         TEXT NOT NULL,   -- 'running' | 'completed' | 'escalated' | 'failed'
    current_step   TEXT,
    step_results   JSONB NOT NULL DEFAULT '{}',
    ledger_ref     TEXT,            -- ledger.events intent_id for audit link
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Triage engine integration

When the triage engine (ADR 0114) surfaces a runbook as a discriminating check with `auto_check: true`, and the runbook is marked `automation.eligible: true`, and the agent's trust tier (ADR 0125) meets `agent_trust_required`, the closure loop (ADR 0126) invokes the runbook executor directly rather than dispatching a single-workflow intent.

```python
# In closure loop PROPOSING stage:
if runbook.automation.eligible and policy.trust_tier >= runbook.agent_trust_required:
    executor.execute(runbook_id, params, actor_id)
else:
    # Fall back to single-step intent or escalate to operator
    compiler.compile(runbook.steps[0].workflow_id, ...)
```

### Platform CLI

```bash
$ lv3 runbook execute renew-tls-certificate --service step-ca
Starting runbook: renew-tls-certificate
  [1/4] check-expiry    → running...  ✓ (days_remaining=6)
  [2/4] renew-cert      → running...  ✓ (new_expiry_days=365)
  [3/4] verify-health   → waiting 15s → ✓ (status=healthy)
  [4/4] update-case     → running...  ✓
Runbook complete. Run ID: run-abc-123

$ lv3 runbook status run-abc-123
$ lv3 runbook approve run-abc-123   # Resume an escalated run
```

## Consequences

**Positive**

- Deterministic, multi-step remediation procedures (certificate renewal, secret rotation, service restart-and-verify) can run autonomously end-to-end without operator involvement.
- Every step result is captured in the run record and ledger. Post-incident analysis has a complete trace: which step was executed, what it returned, whether verification passed.
- Runbook steps that call for operator attention (escalations) produce a specific, actionable Mattermost notification with the step that failed and why, rather than a generic "automation failed" alert.
- Existing prose runbooks are unaffected. Automation front matter is opt-in; runbooks without it remain human-executable references.

**Negative / Trade-offs**

- Runbook authors must write and maintain automation front matter in addition to prose descriptions. For runbooks with complex conditional logic, expressing that logic in YAML `success_condition` strings may be more error-prone than prose.
- Sequential step execution means a runbook that takes 5 minutes per step will take 25 minutes for 5 steps. There is no parallel step execution in the first implementation. Runbooks that benefit from parallelism require custom Windmill workflows instead.
- The `success_condition` evaluation uses a restricted expression evaluator (no arbitrary Python). Complex conditions must be decomposed into multiple steps or pushed into the workflow itself.

## Boundaries

- The runbook executor drives steps through the standard goal compiler → scheduler pipeline. It does not bypass the health check (ADR 0128), conflict detection (ADR 0127), budget enforcement (ADR 0119), or capability policy (ADR 0125).
- Runbook automation front matter is optional. Runbooks are still primarily human-readable documents.
- This ADR does not define how runbooks are authored or stored; those concerns remain in the search fabric (ADR 0121) and documentation practices.

## Related ADRs

- ADR 0048: Command catalog (workflow_ids referenced in runbook steps)
- ADR 0057: Mattermost ChatOps (escalation notifications)
- ADR 0090: Platform CLI (`lv3 runbook` commands)
- ADR 0112: Deterministic goal compiler (each step compiled as an intent)
- ADR 0114: Rule-based incident triage engine (surfaces runbooks; invokes executor when eligible)
- ADR 0115: Event-sourced mutation ledger (run steps recorded)
- ADR 0118: Replayable failure case library (successful run updates cases)
- ADR 0119: Budgeted workflow scheduler (executes each compiled step)
- ADR 0121: Local search and indexing fabric (runbooks indexed; searched by triage)
- ADR 0123: Agent session bootstrap (SessionContext used by executor)
- ADR 0125: Agent capability bounds (trust tier checked against runbook requirement)
- ADR 0126: Observation-to-action closure loop (invokes executor for eligible runbooks)
- ADR 0127: Intent deduplication (conflict check per step)
- ADR 0128: Platform health composite index (health gate checked per step)
