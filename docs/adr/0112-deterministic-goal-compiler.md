# ADR 0112: Deterministic Goal Compiler

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform CLI (ADR 0090) and agent tool registry (ADR 0069) give operators and agents a way to invoke automation. What neither provides is a durable, inspectable contract between what the operator expressed and what the platform actually executes.

Today, an operator types a natural-language instruction or selects a workflow name. That instruction is passed directly to Windmill (ADR 0044) or the platform API gateway (ADR 0092) with no intermediate translation layer. This means:

- **No pre-execution review**: the operator cannot see what the instruction will do before it runs.
- **No risk classification**: the platform has no way to decide whether to auto-run, gate for approval, or reject the instruction before execution begins.
- **No rollback path established upfront**: rollback logic is ad hoc and hidden inside individual playbooks.
- **No scope bounding**: instructions do not declare which hosts, services, or data they are allowed to touch.
- **No reproducibility**: two identical natural-language instructions may produce different behaviours depending on which assistant interprets them.

The goal compiler closes this gap. It is the CPU-only front door for all agent and operator tasks: it translates human expression into a typed, schema-validated execution intent before anything touches the platform.

## Decision

We will introduce a **deterministic goal compiler** as a standalone Python module at `platform/goal_compiler/` that transforms operator input into a typed `ExecutionIntent` struct.

### Intent schema

```python
# platform/goal_compiler/schema.py

@dataclass
class ExecutionIntent:
    id: str                         # UUID, stable across retries
    created_at: str                 # ISO8601
    raw_input: str                  # the original operator expression, verbatim
    action: str                     # canonical verb: deploy | rotate | restart | query | ...
    target: IntentTarget            # host, service, vmid, or group
    scope: IntentScope              # allowed_hosts, allowed_services, allowed_vmids
    preconditions: list[str]        # e.g. "service netbox is healthy", "no active incident"
    risk_class: RiskClass           # LOW | MEDIUM | HIGH | CRITICAL
    allowed_tools: list[str]        # tool IDs from the tool registry (ADR 0069)
    rollback_path: str | None       # rollback workflow ID or None if not applicable
    success_criteria: list[str]     # machine-checkable assertions
    ttl_seconds: int                # intent expires after this many seconds if not executed
    requires_approval: bool         # derived from risk_class and scope
    compiled_by: str                # compiler version string
```

### Compilation pipeline

The compiler runs in three stages, all CPU-only:

1. **Normalisation**: strip whitespace, resolve aliases (e.g. `"the monitoring stack"` → `["grafana", "loki", "prometheus"]`), and lower-case the action verb. The alias table lives in `config/goal-compiler-aliases.yaml` and is version-controlled.

2. **Rule matching**: match the normalised input against an ordered rule table in `config/goal-compiler-rules.yaml`. Each rule declares a pattern (substring or regex), the resulting action verb, the default risk class, the allowed tool set, and the rollback path. The first matching rule wins. If no rule matches, the compiler returns a `PARSE_ERROR` with the unmatched input for operator review.

3. **Scope and precondition injection**: bind the resolved target to the current world-state (ADR 0113) to determine which hosts and services fall within the declared scope. Inject platform-level preconditions (maintenance window check via ADR 0080, active incident check via ADR 0114).

### Rule table format

```yaml
# config/goal-compiler-rules.yaml
- id: deploy-service
  patterns:
    - "deploy {service}"
    - "converge {service}"
    - "apply {service}"
  action: deploy
  default_risk_class: MEDIUM
  allowed_tools: [ansible-playbook, windmill-trigger]
  rollback_path: rollback-service-deployment
  requires_approval_above: MEDIUM

- id: rotate-secret
  patterns:
    - "rotate secret for {service}"
    - "rotate {service} credentials"
  action: rotate
  default_risk_class: HIGH
  allowed_tools: [openbao-rotate, windmill-trigger]
  rollback_path: restore-secret-from-openbao-snapshot
  requires_approval_above: LOW
```

### Integration with the platform CLI

The platform CLI `lv3 run <instruction>` command:

1. Calls the goal compiler with the raw instruction.
2. Displays the compiled `ExecutionIntent` as a YAML summary.
3. If `requires_approval` is true, prompts the operator for explicit confirmation.
4. If approved or auto-runnable, submits the intent to the workflow scheduler (ADR 0119), which enforces budget limits before handing off to Windmill.

### Integration with the agent observation loop

The agent observation loop (ADR 0071) must submit all planned actions through the goal compiler before execution. Raw language expressions must never reach Windmill or the platform API gateway directly. The goal compiler is the mandatory first hop for every programmatic and human-initiated action.

### Error handling

Compilation errors are not silent. Every `PARSE_ERROR` or `SCOPE_ERROR` is written to the mutation ledger (ADR 0115) with the raw input, the failure reason, and the compiler version. This makes mis-compilations auditable and improvable.

## Consequences

**Positive**

- Every action is reviewable before it executes: the compiled intent is a diff-able YAML document.
- Risk classification and approval gating happen at compile time, not inside individual playbooks.
- The rule table is the single place to update intent-to-action mappings; no playbook changes needed for scope adjustments.
- Compilation errors are auditable: patterns that fail to match accumulate in the ledger and drive rule improvements.
- Rollback paths are declared upfront; the workflow scheduler (ADR 0119) can verify rollback workflows exist before starting execution.

**Negative / Trade-offs**

- Novel or ad hoc instructions that match no rule will be rejected until a rule is added; this is intentional but requires ongoing rule maintenance.
- The alias table and rule table must be updated as the platform grows; stale aliases produce silent mis-compilations.
- The compiler introduces latency (sub-second, but non-zero) into every interactive `lv3 run` invocation.

## Boundaries

- The goal compiler is a CPU-only module. It does not call any LLM at runtime. Compilation is deterministic for identical inputs and rule tables.
- The compiler does not execute anything. Execution is delegated to the workflow scheduler (ADR 0119).
- The compiler does not validate that the target actually exists in the live platform; that is the responsibility of the world-state materializer (ADR 0113) and the dry-run diff engine (ADR 0120).

## Related ADRs

- ADR 0048: Command catalog (source of canonical action verb definitions)
- ADR 0069: Agent tool registry (source of allowed tool IDs)
- ADR 0071: Agent observation loop (all agent actions pass through the compiler)
- ADR 0090: Platform CLI (user-facing entry point for compiled intents)
- ADR 0113: World-state materializer (provides scope-binding context)
- ADR 0115: Event-sourced mutation ledger (audit log for compilation errors and compiled intents)
- ADR 0116: Change risk scoring (provides risk_class override when score exceeds rule defaults)
- ADR 0119: Budgeted workflow scheduler (receives compiled intents for execution)
