# ADR 0125: Agent Capability Bounds and Autonomous Action Policy

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform has several automation actors that operate with varying degrees of autonomy:

- The observation loop (ADR 0071) detects drift and emits findings; it currently escalates critical findings for `auto_approve: true` commands.
- The triage engine (ADR 0114) triggers discriminating checks for rules with `auto_check: true`.
- The goal compiler (ADR 0112) compiles intents and routes them through the approval gate based on the risk class returned by the risk scorer (ADR 0116).
- Windmill scripts triggered by agents can call any tool in the tool registry (ADR 0069).

The existing controls are scattered:

- `auto_approve` is a per-command flag in the command catalog (ADR 0048).
- `auto_check` is a per-rule flag in the triage rules (ADR 0114).
- Risk-based approval is computed dynamically at intent compile time.
- Tool registry permissions (ADR 0069) control what tools can be called, but not what workflows can be submitted.

There is no single place that declares, per agent identity: "this agent may read these surfaces, submit these workflow classes, act autonomously up to this risk tier, and must escalate anything above that tier." As the number of autonomous agents grows, this gap creates:

- Invisible trust elevation: an agent that gains access to a high-trust tool call accidentally acquires powers its operator did not intend.
- Unpredictable escalation paths: when an agent reaches the boundary of what it can do, there is no canonical escalation mechanism.
- Audit opacity: the ledger records what was done, but not whether the actor was authorised to do it autonomously or should have escalated.

## Decision

We will define an **agent capability policy** as a per-identity configuration in `config/agent-policies.yaml`. Every agent identity (as declared in ADR 0046) must have a policy entry before it can submit intents to the goal compiler or publish to NATS. The policy enforces what the agent may read, what it may execute autonomously, and what requires human escalation.

### Policy schema

```yaml
# config/agent-policies.yaml

- agent_id: agent/triage-loop
  description: Automated triage triggered on every alert; high read access, low write autonomy
  identity_class: service-agent        # From ADR 0046
  trust_tier: T2                       # T1 (read-only) | T2 (low-risk autonomy) | T3 (medium-risk) | T4 (operator-equivalent)

  read_surfaces:
    - world_state                      # May query world-state materializer
    - ledger                           # May read mutation ledger
    - search                           # May query search fabric
    - loki_logs                        # May query Loki
    - health_probes                    # May call health probe endpoints

  autonomous_actions:
    max_risk_class: LOW                # May autonomously execute intents up to this risk class
    allowed_workflow_tags:
      - diagnostic                     # Only diagnostic workflows, not mutation workflows
      - auto_check                     # Auto-check workflows explicitly tagged for triage
    disallowed_workflow_ids:
      - rollback-service-deployment    # Explicitly prohibited, even if LOW risk
    max_daily_autonomous_executions: 20

  escalation:
    on_risk_above: LOW                 # Escalate if intent risk class exceeds LOW
    escalation_target: mattermost:#platform-incidents
    escalation_event: platform.incident.escalated

- agent_id: agent/observation-loop
  description: Scheduled 4-hourly drift and health observation
  identity_class: service-agent
  trust_tier: T2

  read_surfaces:
    - world_state
    - ledger
    - health_probes
    - search

  autonomous_actions:
    max_risk_class: LOW
    allowed_workflow_tags:
      - auto_remediate                 # Only pre-approved auto-remediation workflows
    max_daily_autonomous_executions: 10

  escalation:
    on_risk_above: LOW
    escalation_target: mattermost:#platform-findings
    escalation_event: platform.findings.observation

- agent_id: agent/claude-code
  description: Interactive Claude Code sessions initiated by an operator
  identity_class: operator-agent       # Acts on behalf of a named operator
  trust_tier: T3

  read_surfaces:
    - world_state
    - ledger
    - search
    - loki_logs
    - health_probes
    - netbox
    - opentofu_state

  autonomous_actions:
    max_risk_class: MEDIUM             # May execute MEDIUM-risk intents without per-step approval
    allowed_workflow_tags:
      - diagnostic
      - converge
      - rotate_secret
    disallowed_workflow_ids:
      - destroy-vm                     # Never autonomously, regardless of risk class
      - wipe-database
    max_daily_autonomous_executions: 50

  escalation:
    on_risk_above: MEDIUM
    escalation_target: operator        # Pause and ask the operator
    escalation_event: platform.intent.rejected
```

### Trust tiers

| Tier | Description | Approval requirement |
|---|---|---|
| T1 | Read-only | No mutation access |
| T2 | Low-risk autonomy | AUTO for LOW; escalate MEDIUM+ |
| T3 | Medium-risk autonomy | AUTO for LOW+MEDIUM; escalate HIGH+ |
| T4 | Operator-equivalent | AUTO for LOW+MEDIUM+HIGH; escalate CRITICAL only |

T4 is reserved for named human operators acting through the CLI or ops portal. No unattended agent may hold T4 trust.

### Policy enforcement

The goal compiler (ADR 0112) checks the agent policy before compiling an intent:

```python
def compile(self, instruction: str, actor_id: str, context: SessionContext) -> ExecutionIntent:
    policy = PolicyClient().get(actor_id)

    intent = self._compile_internal(instruction, context)

    # Check if actor is allowed to read the surfaces it needs
    for surface in intent.required_surfaces:
        if surface not in policy.read_surfaces:
            raise CapabilityDenied(f"{actor_id} cannot read surface '{surface}'")

    # Check if workflow is explicitly prohibited
    if intent.workflow_id in policy.disallowed_workflow_ids:
        raise CapabilityDenied(f"{actor_id} is prohibited from running '{intent.workflow_id}'")

    # Check risk class against autonomous action limit
    if intent.risk_class.value > policy.autonomous_actions.max_risk_class.value:
        return self._escalate(intent, policy)

    return intent
```

### Escalation flow

When an agent's policy requires escalation, the goal compiler:

1. Publishes `platform.intent.rejected` to NATS (ADR 0124) with `reason: capability_bound_exceeded`.
2. Posts the compiled intent summary to the escalation target (e.g., Mattermost channel, or pauses and returns control to an interactive operator session).
3. Writes the rejected intent to the ledger (ADR 0115) with `status: escalated`.
4. Optionally re-submits the intent with elevated trust if the operator approves via the ops portal (ADR 0093).

### Daily execution cap

The policy includes `max_daily_autonomous_executions` to prevent runaway agent loops. The scheduler (ADR 0119) increments a counter in Postgres for the agent identity, keyed by calendar day. If the cap is reached, subsequent autonomous submissions are rejected until the next UTC day. Manual operator-approved executions do not count toward the cap.

### Policy as code

`config/agent-policies.yaml` is subject to the same validation pipeline (ADR 0031) as all other config files. Policy changes require a pull request and pass schema validation before merge. Operators cannot widen an agent's policy at runtime; the change must go through the repo.

## Consequences

**Positive**

- The trust boundary for every agent is explicit, reviewable, and version-controlled. Auditors can point to the exact policy version active during any past incident.
- Trust elevation is impossible without a code change. An agent cannot acquire HIGH-risk execution capability because a command happens to be tagged `auto_check`.
- The daily cap prevents a feedback loop where a triage agent repeatedly triggers the same auto-check workflow on a false-positive alert.
- Escalation paths are declared, not emergent; when an agent reaches a boundary, both the agent and the operator know exactly what happened and why.

**Negative / Trade-offs**

- Every new agent identity requires a policy entry before it can do anything. This is intentional friction but adds setup overhead when deploying a new workflow class.
- The `max_daily_autonomous_executions` cap is coarse-grained. An agent that legitimately needs to run 100 diagnostic checks on a bad day will hit the cap. Operators can override for a specific incident, but the escape valve is manual.
- Policy changes require a pull request. For emergency situations, there is no runtime escalation mechanism; the operator must either approve the action manually or raise the cap via a fast-tracked PR.

## Boundaries

- This ADR governs autonomous agent action policy. It does not govern operator permissions; those are managed by Keycloak (ADR 0056) and the command catalog (ADR 0048).
- The policy file is the authoritative source. Tool registry entries (ADR 0069) remain but are secondary; the policy layer evaluates first.
- Agents that operate interactively in a Claude Code session inherit the session operator's approval authority for anything above their autonomous threshold; the operator is the escalation target in that context.

## Related ADRs

- ADR 0046: Identity classes (agent_id and identity_class fields)
- ADR 0048: Command catalog (workflow tags referenced in policy allowed_workflow_tags)
- ADR 0056: Keycloak SSO (operator identity; policy T4 reserved for operators)
- ADR 0069: Agent tool registry (policy layer evaluated before tool registry lookup)
- ADR 0071: Agent observation loop (agent/observation-loop policy example)
- ADR 0090: Platform CLI (policy check at CLI invocation for operator-agent sessions)
- ADR 0093: Interactive ops portal (operator approval of escalated intents)
- ADR 0112: Deterministic goal compiler (policy check enforced here)
- ADR 0114: Incident triage engine (agent/triage-loop policy example)
- ADR 0115: Event-sourced mutation ledger (rejected intents recorded)
- ADR 0116: Change risk scoring (risk class compared against policy max_risk_class)
- ADR 0119: Budgeted workflow scheduler (daily cap counter maintained here)
- ADR 0124: Platform event taxonomy (platform.intent.rejected published on escalation)
