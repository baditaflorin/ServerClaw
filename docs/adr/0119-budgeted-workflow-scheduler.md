# ADR 0119: Budgeted Workflow Scheduler

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.118.0
- Implemented In Platform Version: 0.130.20
- Implemented On: 2026-03-26
- Date: 2026-03-24

## Context

Windmill (ADR 0044) is the platform's workflow execution engine. It runs operator-triggered jobs, agent-initiated workflows, nightly maintenance tasks, and the automation invoked by the goal compiler (ADR 0112). Windmill has basic timeout and concurrency settings per workflow, but the platform has no systematic, cross-workflow enforcement of execution budgets.

The consequence is that runaway automation is possible:

- A retry loop that never converges can consume a Windmill worker for hours.
- A workflow that touches every host in a blast radius without a host-count cap can saturate the entire platform.
- Concurrent deployments to overlapping service sets can cause race conditions on shared config files.
- An agent that spawns sub-workflows recursively has no hard depth limit.
- A rollback that itself fails has no mechanism to prevent a rollback-of-rollback loop.

These are not theoretical concerns. Agent-driven automation without explicit budgets is a known failure mode in autonomous systems: the first time a loop fails to terminate, the cost of the failure is proportional to how much the platform trusts the loop.

Explicit budgets convert "automation that might loop forever" into "automation that terminates predictably and escalates when it cannot complete within declared limits."

## Decision

We will implement a **budgeted workflow scheduler** as a thin orchestration layer between the goal compiler (ADR 0112) and Windmill (ADR 0044). The scheduler receives a compiled `ExecutionIntent`, enforces budget constraints, and either submits the job to Windmill or rejects it with a budget violation reason.

The first repository implementation in `0.118.0` lands under [`platform/scheduler/`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/scheduler), updates [`scripts/lv3_cli.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/lv3_cli.py) to route `lv3 run` through the scheduler, and adds a watchdog worker entry point at [`windmill/scheduler/watchdog-loop.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/windmill/scheduler/watchdog-loop.py). When `LV3_LEDGER_DSN` is available, the implementation uses Postgres advisory transaction locks; otherwise it falls back to repo-local file locks so the scheduler still enforces concurrency in controller-only test and development environments.

### Budget schema

Every workflow in the workflow catalog (ADR 0048) declares a `budget` block. The scheduler enforces these limits:

```yaml
# In config/workflow-catalog.json, extended with budget declarations

{
  "id": "converge-netbox",
  "description": "Deploy or converge the NetBox service",
  "playbook": "playbooks/netbox.yml",
  "budget": {
    "max_duration_seconds": 300,
    "max_steps": 50,
    "max_concurrent_instances": 1,
    "max_touched_hosts": 2,
    "max_restarts": 0,
    "max_rollback_depth": 1,
    "escalation_action": "notify_and_abort"
  }
}
```

| Budget field | Meaning | Enforcement |
|---|---|---|
| `max_duration_seconds` | Wall-clock time limit for the entire workflow | Windmill job timeout + scheduler watchdog |
| `max_steps` | Maximum number of Ansible tasks or workflow steps that may complete | Step counter in the workflow wrapper |
| `max_concurrent_instances` | Maximum number of simultaneous instances of this workflow | Scheduler concurrency lock (Postgres advisory lock) |
| `max_touched_hosts` | Maximum number of distinct Ansible hosts the workflow may contact | Pre-execution inventory check |
| `max_restarts` | Maximum number of times the scheduler will retry a failed workflow | Retry counter in the scheduler |
| `max_rollback_depth` | Maximum nesting depth of rollback-of-rollback chains | Rollback chain depth counter |
| `escalation_action` | What to do when a limit is exceeded | `notify_and_abort` \| `abort_silently` \| `escalate_to_operator` |

### Scheduler lifecycle

```
CompiledIntent
     │
     ▼
┌─────────────────────────────┐
│  BudgetedWorkflowScheduler  │
│                             │
│  1. Load workflow budget     │
│  2. Acquire concurrency lock │
│  3. Pre-flight host check    │
│  4. Submit to Windmill       │
│  5. Watchdog loop            │
│     ├─ check duration        │
│     ├─ check step count      │
│     └─ check touched hosts   │
│  6. On budget violation:     │
│     ├─ abort Windmill job    │
│     ├─ write violation event │
│     └─ escalate per policy   │
└─────────────────────────────┘
     │
     ▼
  LedgerWriter  ──► execution.started / execution.completed /
                    execution.budget_exceeded / execution.aborted
```

### Concurrency lock

The scheduler uses a Postgres advisory lock keyed on the workflow ID to enforce `max_concurrent_instances`. Before submitting a job to Windmill, the scheduler attempts to acquire `pg_try_advisory_lock(workflow_id_hash)`. If the lock is held (another instance is running), the scheduler returns a `CONCURRENCY_LIMIT` rejection immediately rather than queuing.

Queuing is intentionally not implemented. If a workflow cannot start immediately, the goal compiler returns control to the operator or agent with a `WORKFLOW_BUSY` status. The agent observation loop (ADR 0071) is responsible for retry timing.

### Watchdog

The scheduler runs a lightweight watchdog loop in a separate Windmill workflow that polls active jobs every 30 seconds:

```python
# windmill/scheduler/watchdog.py

for job in active_jobs():
    elapsed = now() - job.started_at
    if elapsed > job.budget.max_duration_seconds:
        windmill.cancel_job(job.id)
        ledger.write(event_type="execution.budget_exceeded",
                     target_id=job.workflow_id,
                     metadata={"reason": "max_duration_seconds", "elapsed_s": elapsed})
        escalate(job, reason="duration_exceeded")
```

### Rollback depth guard

When the goal compiler compiles a rollback intent, it passes the parent intent's `actor_intent_id`. The scheduler checks the ledger for the chain of intents linked by `actor_intent_id` and counts the rollback depth. If the depth exceeds `max_rollback_depth`, the rollback is blocked and an operator is notified.

This prevents the failure mode of "rollback fails → operator triggers another rollback → second rollback fails → third rollback begins" — a real failure pattern in automated operations.

### Default budgets

Workflows that have no `budget` block in the catalog use the following platform defaults:

```yaml
# config/workflow-defaults.yaml
default_budget:
  max_duration_seconds: 600
  max_steps: 200
  max_concurrent_instances: 3
  max_touched_hosts: 10
  max_restarts: 1
  max_rollback_depth: 1
  escalation_action: notify_and_abort
```

The default budget is deliberately conservative. Workflows that need more capacity must declare explicit budgets, which makes their resource appetite visible in code review.

## Consequences

**Positive**

- Runaway loops are impossible by construction. Every workflow has a hard wall-clock limit and a step limit.
- The concurrency lock prevents two simultaneous deployments to the same service from racing on shared config.
- Rollback chains are bounded. The "rollback of rollback" failure mode is eliminated.
- Budget violations are auditable events in the ledger; over time they reveal which workflows are consistently underpowered and need budget increases.

**Negative / Trade-offs**

- The default budget is conservative. Legitimate long-running workflows (Packer image builds, large backup operations) will hit the defaults and need explicit budget declarations. This requires discipline from workflow authors.
- The concurrency lock is non-queuing by design. If two agents attempt the same workflow simultaneously, the second one is rejected rather than queued. The agent must implement its own retry logic.
- The watchdog is a Windmill workflow polling every 30 seconds; it introduces up to 30 seconds of overage before a violation is detected and the job cancelled.

## Boundaries

- The budgeted scheduler enforces execution limits. It does not make decisions about what to execute; that is the goal compiler's (ADR 0112) responsibility.
- Budget declarations live in the workflow catalog (ADR 0048). Changing a workflow's budget is a code change, not a runtime configuration change.
- The scheduler does not rate-limit read-only or diagnostic workflows; budgets apply only to workflows with `execution_class: mutation` in the workflow catalog.

## Related ADRs

- ADR 0044: Windmill (workflow execution engine; jobs submitted here)
- ADR 0048: Command catalog (workflow declarations and budget blocks)
- ADR 0058: NATS event bus (escalation notifications)
- ADR 0071: Agent observation loop (handles WORKFLOW_BUSY rejections with retry logic)
- ADR 0098: Postgres HA (advisory locks for concurrency control)
- ADR 0112: Deterministic goal compiler (submits compiled intents to the scheduler)
- ADR 0115: Event-sourced mutation ledger (execution lifecycle and budget violation events)
- ADR 0116: Change risk scoring (risk class influences scheduler approval gate behaviour)
