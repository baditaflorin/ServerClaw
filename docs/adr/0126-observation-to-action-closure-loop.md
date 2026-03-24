# ADR 0126: Observation-to-Action Closure Loop

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform has working implementations of every major stage in the automation lifecycle:

- **Observe**: the observation loop (ADR 0071) detects drift, health failures, and staleness every 4 hours.
- **Triage**: the triage engine (ADR 0114) correlates signals, ranks hypotheses, and proposes discriminating checks.
- **Compile**: the goal compiler (ADR 0112) translates instructions into typed `ExecutionIntent` structs.
- **Approve**: the approval gate (ADR 0048) gates mutation intents on risk class.
- **Execute**: the budgeted scheduler (ADR 0119) submits jobs to Windmill within budget constraints.
- **Record**: the ledger (ADR 0115) captures every event in the lifecycle.
- **Learn**: the case library (ADR 0118) stores resolved failures with root cause and remediation.

However, these stages are **not connected as a pipeline**. They are separate Windmill workflows, triggered by different mechanisms, with no shared state machine governing the transition from one stage to the next. Specifically:

- An observation finding from the observation loop does not automatically trigger the triage engine.
- A triage report does not automatically propose an intent to the goal compiler.
- A completed execution does not automatically trigger a verification step.
- A verified remediation does not automatically update the case library.
- If any intermediate stage fails, there is no protocol for returning to the previous stage or escalating.

The consequence is that the loop exists conceptually but not operationally. An observation finding sits in Mattermost until an operator or agent manually picks it up and begins the next stage. This manual handoff is the primary source of MTTR variance: incidents that happen to be noticed quickly get resolved quickly; those that slip through sit open for hours.

## Decision

We will implement an **observation-to-action closure loop** as a durable Windmill workflow state machine. The state machine connects the existing pipeline stages into an explicit, auditable lifecycle with defined transitions, retry policies, and escalation paths.

### State machine

```
┌──────────────┐
│   OBSERVED   │  ◄── observation loop finding OR alert from ADR 0097
└──────┬───────┘
       │ auto-trigger triage (always)
       ▼
┌──────────────┐
│   TRIAGED    │  ◄── triage engine produces ranked hypotheses
└──────┬───────┘
       │ if auto_check=true for top hypothesis
       │   AND agent policy allows (ADR 0125)
       ▼               else → ESCALATED_FOR_APPROVAL
┌──────────────┐
│  PROPOSING   │  ◄── goal compiler compiles discriminating check or remediation intent
└──────┬───────┘
       │ if risk_class ≤ agent autonomous threshold
       │   AND no conflict detected (ADR 0127)
       ▼               else → ESCALATED_FOR_APPROVAL
┌──────────────┐
│  EXECUTING   │  ◄── scheduler submits to Windmill
└──────┬───────┘
       │ on completion
       ▼
┌──────────────┐
│  VERIFYING   │  ◄── run verification check (health probe OR search query OR metric)
└──────┬───────┘
       │ if verification passes
       ▼               else → back to TRIAGED (with updated signals)
┌──────────────┐
│   RESOLVED   │  ◄── update case library, close GlitchTip incident
└──────────────┘
       │ if case library already has a match
       ▼
┌──────────────────┐
│  CASE_PROMOTED   │  ◄── auto-promote confidence of matching case
└──────────────────┘
```

States `ESCALATED_FOR_APPROVAL` and `BLOCKED` are terminal pending states that require operator input:

```
ESCALATED_FOR_APPROVAL  →  operator approves  →  PROPOSING
                        →  operator rejects   →  CLOSED_NO_ACTION
BLOCKED                 →  operator resolves  →  appropriate stage
                        →  operator closes    →  CLOSED_NO_ACTION
```

### Loop record schema

Each run of the closure loop creates a `loop.runs` record:

```sql
CREATE TABLE loop.runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_type    TEXT NOT NULL,   -- 'observation_finding' | 'alert' | 'manual'
    trigger_ref     TEXT NOT NULL,   -- Finding ID, alert ID, or operator intent ID
    service_id      TEXT NOT NULL,
    current_state   TEXT NOT NULL,   -- State machine state
    context_id      UUID,            -- SessionContext from bootstrap (ADR 0123)
    triage_report   JSONB,           -- Output of triage engine
    proposed_intent JSONB,           -- Compiled intent (if reached PROPOSING)
    execution_ref   TEXT,            -- Windmill job ID (if reached EXECUTING)
    verification_result JSONB,
    resolution      JSONB,
    escalation_reason TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ
);
```

### State transition rules

| From → To | Condition | Actor |
|---|---|---|
| OBSERVED → TRIAGED | Always | Automatic (triage engine) |
| TRIAGED → PROPOSING | top hypothesis has `auto_check: true` AND agent policy allows | Automatic |
| TRIAGED → ESCALATED | any other case | Automatic → awaits operator |
| PROPOSING → EXECUTING | risk_class ≤ agent threshold AND no conflict | Automatic |
| PROPOSING → ESCALATED | risk too high OR conflict detected | Automatic → awaits operator |
| EXECUTING → VERIFYING | workflow completed (success or partial) | Automatic |
| VERIFYING → RESOLVED | verification check passes | Automatic |
| VERIFYING → TRIAGED | verification fails; re-triage with fresh signals | Automatic (max 3 cycles) |
| VERIFYING → BLOCKED | re-triage limit reached | Automatic → awaits operator |

### Verification step

After execution completes, the loop runs a lightweight verification check before marking the run `RESOLVED`. The verification strategy is determined by the executed workflow's `verification` block in the workflow catalog:

```yaml
# In config/workflow-catalog.json
{
  "id": "converge-netbox",
  "verification": {
    "type": "health_probe",
    "target": "netbox",
    "wait_seconds": 30,          # Grace period before checking
    "pass_condition": "status == 'healthy'"
  }
}
```

If no `verification` block is declared, the loop polls the health probe of the affected service. If the service has no health probe, the loop transitions to `RESOLVED` with a `verification_skipped` flag and a warning.

### Re-triage cycle

If verification fails, the loop re-fetches fresh signals from the world-state materializer and runs the triage engine again. The second triage pass adds the failed execution to the signal set (`last_auto_check_failed: true`). A maximum of 3 re-triage cycles are allowed; after that, the loop enters `BLOCKED` and escalates to an operator.

### Ledger integration

Every state transition is written to the mutation ledger (ADR 0115) with `event_type: loop.state_transition`:

```json
{
  "event_type": "loop.state_transition",
  "run_id": "uuid",
  "from_state": "TRIAGED",
  "to_state": "PROPOSING",
  "trigger": "auto_check: tls-cert-expiry matched",
  "ts": "2026-03-24T14:35:00Z"
}
```

### NATS events

The loop publishes to the canonical event taxonomy (ADR 0124):

- `platform.incident.opened` when a run enters TRIAGED.
- `platform.incident.escalated` when a run enters ESCALATED_FOR_APPROVAL or BLOCKED.
- `platform.incident.resolved` when a run enters RESOLVED.

### Manual trigger

Operators can manually inject a run into the loop at any stage:

```bash
$ lv3 loop start --trigger manual --service netbox --state OBSERVED
$ lv3 loop status <run_id>
$ lv3 loop approve <run_id>     # Move ESCALATED → PROPOSING
$ lv3 loop close <run_id>       # Mark CLOSED_NO_ACTION with a reason
```

## Consequences

**Positive**

- Every observation finding now has a durable record of what happened next: was it triaged, did it lead to an action, did that action succeed? The platform's response to every finding is auditable.
- MTTR improves structurally: the handoff between stages is automatic for pre-approved, low-risk scenarios. Operators are only pulled in when the loop cannot proceed autonomously.
- The re-triage cycle handles the common case where the first remediation attempt is insufficient without requiring operator attention.
- The state machine makes escalation paths explicit: operators receive a Mattermost notification with the exact run state and a direct link to approve or close it.

**Negative / Trade-offs**

- The state machine adds complexity. A platform that previously had loose, independently-testable components now has a coordination layer that can fail. The loop itself must be monitored and have its own health probe.
- The maximum 3 re-triage cycles is arbitrary. A persistent failure mode (e.g., a flapping service that keeps failing after each auto-remediation attempt) will trigger 3 expensive triage-execute-verify cycles before escalating.
- The verification step introduces a mandatory wait period before closure. A workflow that fixes a service in 30 seconds may take 2 minutes to be marked RESOLVED due to the grace period and verification poll. This is correct behavior but may surprise operators who expect immediate closure.

## Boundaries

- The closure loop orchestrates existing components. It does not implement triage logic, goal compilation, or execution; those remain in their respective ADRs.
- The loop state machine governs automated scenarios. Operators working directly in the CLI or ops portal bypass the loop; their actions are recorded in the ledger but do not create loop run records.
- The loop's re-triage limit (3 cycles) is configurable per service in `config/service-capability-catalog.json` but has a platform-level maximum of 5.

## Related ADRs

- ADR 0048: Command catalog (verification block in workflow entries)
- ADR 0057: Mattermost ChatOps (escalation notifications)
- ADR 0061: GlitchTip (incident opened/closed by loop state transitions)
- ADR 0064: Health probe contracts (default verification mechanism)
- ADR 0071: Agent observation loop (primary trigger source)
- ADR 0090: Platform CLI (`lv3 loop` commands)
- ADR 0097: Alerting routing (secondary trigger source via alert events)
- ADR 0112: Deterministic goal compiler (PROPOSING stage)
- ADR 0114: Rule-based incident triage engine (TRIAGED stage)
- ADR 0115: Event-sourced mutation ledger (state transitions recorded)
- ADR 0118: Replayable failure case library (RESOLVED stage updates cases)
- ADR 0119: Budgeted workflow scheduler (EXECUTING stage)
- ADR 0123: Agent session bootstrap (context_id attached to each run)
- ADR 0124: Platform event taxonomy (incident events published)
- ADR 0125: Agent capability bounds (determines auto vs. escalate transitions)
- ADR 0127: Intent deduplication (conflict check before EXECUTING)
