# ADR 0129: Runbook Automation Executor

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.132.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Date: 2026-03-25

## Context

The platform has a growing library of runbooks under [`docs/runbooks/`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks), but execution is still too manual for deterministic, repeatable procedures. Operators can already run one workflow at a time through `lv3 run` and Windmill, yet the repository lacked a stateful layer that can:

1. load one structured runbook definition
2. render step inputs from run-time parameters and previous step outputs
3. execute each step in order and verify its declared success condition
4. persist run state so an escalated run can be resumed later
5. emit a durable execution trace

## Decision

We will implement a **runbook automation executor** in repository-managed Python with:

- a structured runbook loader that accepts YAML, JSON, and Markdown front matter definitions
- a sequential executor that runs each step through Windmill's synchronous `run_wait_result` API
- a file-backed run store under `.local/runbooks/runs/`
- mutation-audit events for run start, resume, completion, and failed or escalated steps
- operator entrypoints through `lv3 runbook execute|status|approve`
- a Windmill wrapper at [`config/windmill/scripts/runbook-executor.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/windmill/scripts/runbook-executor.py)

The first integrated implementation lands as [`scripts/runbook_executor.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/runbook_executor.py). The repository already ships ADR 0119 scheduler and ADR 0115 ledger primitives elsewhere, but the current runbook executor keeps its persisted run state intentionally local in `.local/runbooks/runs/*.json` while emitting its execution trace through the existing mutation-audit path. That keeps the operator contract small and works in both controller-local and mounted-worker checkouts.

### Runbook shape

```yaml
id: renew-certificate
title: Renew a service certificate
automation:
  eligible: true
steps:
  - id: check-expiry
    workflow_id: check-cert-expiry
    params:
      service: "{{ params.service }}"
    success_condition: "result.days_remaining <= 14"
    on_failure: escalate

  - id: renew-cert
    workflow_id: renew-service-cert
    params:
      service: "{{ params.service }}"
      previous_days: "{{ steps.check-expiry.result.days_remaining }}"
    success_condition: "result.new_expiry_days >= 90"
```

### Execution model

For each step, the executor:

1. renders the step parameters from the run parameters and any previous `steps.<step_id>.result` values
2. optionally waits for `wait_seconds`
3. executes the declared Windmill workflow
4. evaluates the step's `success_condition` with a restricted expression evaluator
5. stores the step result, attempt count, and timestamps in the persisted run record

Supported failure strategies:

| Strategy | Behaviour |
| --- | --- |
| `escalate` | stop the run, mark it escalated, and allow later `approve` resume |
| `retry_once` | run the step one more time, then escalate if it still fails |
| `skip` | mark the step skipped and continue, only for diagnostic steps |
| `continue` | record a warning and continue |
| `rollback` | run the declared rollback workflow, then escalate |

### Persisted state

Each run is written to `.local/runbooks/runs/<run_id>.json` with:

- runbook id and source path
- input params
- current status
- current step and next step index
- per-step execution records
- append-only history entries for each finished step

`lv3 runbook approve <run_id>` resumes an escalated run from the failed step while preserving the previous attempt count.

## Consequences

**Positive**

- Deterministic multi-step procedures can execute from repository-managed definitions instead of ad hoc shell translation.
- Operators have a durable, inspectable run record for every structured runbook execution.
- Escalated runs are resumable instead of forcing a manual restart from step 1.
- YAML and JSON definitions work well for machine-authored runbooks, while Markdown front matter keeps documentation-first authoring possible.

**Negative / Trade-offs**

- The current persisted run store is repo-local state rather than a shared database-backed service.
- Steps still execute sequentially; parallel branches remain out of scope.
- Success conditions use a restricted expression subset by design.

## Boundaries

- The executor does not invent workflow contracts. Every step must target an existing cataloged workflow or an explicit Windmill path.
- Prose-only runbooks remain valid documentation and are not executed unless they add structured front matter.
- Live application of the executor on the running platform is separate from repository implementation.

## Related ADRs

- ADR 0044: Windmill workflow runtime
- ADR 0066: Mutation audit log
- ADR 0090: Platform CLI
- ADR 0115: Event-sourced mutation ledger
- ADR 0119: Budgeted workflow scheduler
