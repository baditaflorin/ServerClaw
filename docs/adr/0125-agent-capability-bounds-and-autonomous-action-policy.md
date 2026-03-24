# ADR 0125: Agent Capability Bounds and Autonomous Action Policy

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.122.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

The platform has several automation actors that operate with varying degrees of autonomy:

- the observation loop (ADR 0071) detects drift and emits findings
- the triage engine (ADR 0114) triggers discriminating checks for rules with `auto_check: true`
- the goal compiler (ADR 0112) compiles intents and routes them through approval based on risk
- Windmill scripts and direct `lv3 run` workflow invocations can submit work into the same control plane

Before this ADR, the trust boundary for those actors was scattered across workflow metadata, triage allowlists, and human convention. There was no single repo-managed answer to:

- which read surfaces one automation identity may depend on
- which workflow classes it may execute autonomously
- which specific workflows are always prohibited
- when autonomy must stop and escalate
- how many autonomous actions are allowed in one UTC day

That gap made trust elevation hard to review and autonomous behavior hard to audit.

## Decision

We will define an **agent capability policy** as a per-identity configuration in [`config/agent-policies.yaml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/agent-policies.yaml). Every automation identity must have a policy entry before it can submit autonomous work through the goal compiler or scheduler.

The first repository implementation in `0.122.0` lands in:

- [`config/agent-policies.yaml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/agent-policies.yaml)
- [`platform/agent_policy/`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/agent_policy)
- [`platform/goal_compiler/compiler.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/goal_compiler/compiler.py)
- [`platform/scheduler/scheduler.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/scheduler/scheduler.py)
- [`scripts/lv3_cli.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/lv3_cli.py)

### Policy schema

Each policy entry defines:

- `agent_id`
- `description`
- `identity_class`
- `trust_tier`
- `read_surfaces`
- `autonomous_actions.max_risk_class`
- `autonomous_actions.allowed_workflow_tags`
- `autonomous_actions.disallowed_workflow_ids`
- `autonomous_actions.max_daily_autonomous_executions`
- `escalation.on_risk_above`
- `escalation.escalation_target`
- `escalation.escalation_event`

### Enforcement model

The implementation applies the same policy contract at both action-entry surfaces:

1. The goal compiler checks compiled natural-language intents before autonomous execution is accepted.
2. The budgeted workflow scheduler checks direct workflow submissions too, so bypassing the compiler does not bypass policy.

The runtime enforces:

- required read surfaces
- allowed workflow tags
- explicit workflow deny lists
- autonomous risk ceilings
- daily autonomous execution caps

### Escalation behavior

When an autonomous action exceeds the actor's risk ceiling, the runtime does not execute it. It returns a structured escalation decision containing:

- `reason: capability_bound_exceeded`
- the configured escalation target
- the configured escalation event name

Hard denials, such as missing surface access or a prohibited workflow ID, return a denial decision instead.

### Daily autonomous cap

The scheduler maintains a repo-local fallback counter at:

- `.local/state/agent-policy/daily-autonomous-executions.json`

The counter is keyed by UTC date and actor ID. Manual operator-approved executions do not consume the cap.

## Consequences

### Positive

- The trust boundary for every automation identity is now explicit and version-controlled.
- Autonomous actions are bounded by both workflow class and risk tier, not only by ad hoc workflow metadata.
- Direct workflow execution and natural-language compilation now share the same policy gate.
- Out-of-bounds autonomous actions are testable and auditable.

### Negative / Trade-offs

- New agent identities now require a policy entry before they can operate.
- Workflow authors need to keep `tags` and `required_read_surfaces` current in the workflow catalog for precise enforcement.
- The daily cap currently uses a repo-local fallback store; a future live rollout should move the same contract onto Postgres for durable multi-runner accounting.

## Boundaries

- This ADR governs autonomous agent action policy, not human SSO or command-catalog approval policy.
- The policy file is authoritative for automation identity bounds.
- Keycloak, the command catalog, and risk scoring remain in place; this policy layer evaluates before autonomous execution is allowed to proceed.

## Related ADRs

- ADR 0046: Identity classes
- ADR 0069: Agent tool registry
- ADR 0071: Agent observation loop
- ADR 0090: Platform CLI
- ADR 0112: Deterministic goal compiler
- ADR 0114: Incident triage engine
- ADR 0115: Event-sourced mutation ledger
- ADR 0116: Change risk scoring
- ADR 0119: Budgeted workflow scheduler
