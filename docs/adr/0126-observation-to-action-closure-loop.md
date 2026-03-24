# ADR 0126: Observation-to-Action Closure Loop

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.125.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

The platform already had the major pieces needed to react to findings:

- ADR 0071 observation emits structured findings
- ADR 0114 triage ranks likely causes and safe auto-checks
- ADR 0112 compiles remediation instructions into typed intents
- ADR 0119 submits approved workflows through the budgeted scheduler
- ADR 0115 records lifecycle events in the ledger

What was missing was the durable loop between those stages. A finding could be observed and triaged, but there was no single run record that answered:

- was the finding picked up automatically
- did it lead to an auto-check or a remediation proposal
- did the action complete
- did verification confirm the goal was achieved
- when did the loop stop and why

Without that loop, operators had to bridge observation, triage, execution, and verification manually.

## Decision

We implement a durable **closure loop** under [`platform/closure_loop/`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/closure_loop) and expose it through:

- [`config/windmill/scripts/platform-observation-loop.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/platform-observation-loop.py) for observation-driven execution
- [`scripts/lv3_cli.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/lv3_cli.py) via `lv3 loop start|status|approve|close`
- repo-local durable state at `.local/state/closure-loop/runs.json`

The implemented state machine is:

`OBSERVED -> TRIAGED -> PROPOSING -> EXECUTING -> VERIFYING -> RESOLVED`

with operator-held states:

- `ESCALATED_FOR_APPROVAL`
- `BLOCKED`
- `CLOSED_NO_ACTION`

### First repository implementation

The first implementation is intentionally thin and reuses current repo surfaces instead of waiting for later ADRs:

- triage uses ADR 0114's existing `build_report()`
- autonomous policy reads `config/agent-policies.yaml`, with repo-local defaults for the observation loop and CLI operators
- conflict detection uses active closure-loop runs for the same service until ADR 0127 lands
- health verification uses the existing `service_health` world-state surface until ADR 0128 lands

That keeps the loop operational on current `main` while preserving the future integration path.

### Goal termination

The loop now terminates explicitly on goal achievement:

- if the affected service is already healthy by the time the run reaches TRIAGED, the run resolves without action
- after EXECUTING, VERIFYING checks service health or the workflow verification block from `config/workflow-catalog.json`
- a successful verification writes the resolution and stops the run instead of re-entering triage
- failed verification re-triages at most 3 times per service, capped at 5 by catalog override, then blocks for operator input

This closes the failure mode where an observation-driven sequence could continue cycling after the desired service state had already been restored.

### Recording

Every state transition writes:

- a durable run update in `.local/state/closure-loop/runs.json`
- `loop.state_transition` into the ledger
- `incident.opened`, `incident.escalated`, and `incident.resolved` ledger events at the corresponding milestones
- `platform.incident.*` NATS subjects when NATS is configured

## Consequences

**Positive**

- Observation findings now produce a durable response record instead of an ephemeral chat handoff.
- Auto-check paths can complete end-to-end without a human in the middle.
- Operators can inspect, approve, or close paused runs through the same CLI.
- Verification is explicit, and successful goal completion stops the loop deterministically.

**Trade-offs**

- The first implementation uses repo-local fallbacks for policy, conflict, and health safety rather than the fuller ADR 0125/0127/0128 runtimes.
- Case-library promotion is not automatic yet; resolved runs are recorded and emitted, but ADR 0118 integration remains a follow-up.
- Active-conflict detection is service-scoped rather than resource-claim-scoped until ADR 0127 is implemented.

## Related ADRs

- ADR 0048: Command catalog
- ADR 0064: Health probe contracts
- ADR 0071: Agent observation loop
- ADR 0090: Platform CLI
- ADR 0112: Deterministic goal compiler
- ADR 0114: Rule-based incident triage engine
- ADR 0115: Event-sourced mutation ledger
- ADR 0119: Budgeted workflow scheduler
