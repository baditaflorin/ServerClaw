# ADR 0112: Deterministic Goal Compiler

- Status: Accepted
- Implementation Status: Partial Implemented
- Implemented In Repo Version: 0.117.1
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-24
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

We will introduce a deterministic goal compiler as a Python module rooted at `platform/goal_compiler/` that transforms operator input into a typed `ExecutionIntent` struct.

### Intent schema

```python
@dataclass
class ExecutionIntent:
    id: str
    created_at: str
    raw_input: str
    action: str
    target: IntentTarget
    scope: IntentScope
    preconditions: list[str]
    risk_class: RiskClass
    allowed_tools: list[str]
    rollback_path: str | None
    success_criteria: list[str]
    ttl_seconds: int
    requires_approval: bool
    compiled_by: str
```

### Compilation pipeline

The compiler runs in three CPU-only stages:

1. **Normalisation**: collapse whitespace, lower-case the instruction, and apply the version-controlled alias table from `config/goal-compiler-aliases.yaml`.
2. **Rule matching**: match the normalised instruction against ordered rules in `config/goal-compiler-rules.yaml`. The first matching template, regex, or substring rule wins.
3. **Scope and precondition injection**: bind the matched target to repository catalogs and best-effort world-state data, then inject maintenance-window and active-incident preconditions.

### Integration with the platform CLI

The platform CLI `lv3 run <instruction>` command now:

1. Compiles the raw instruction into an `ExecutionIntent`.
2. Displays the compiled intent as YAML before execution.
3. Writes `intent.compiled` to the ledger for every run, including dry-runs.
4. Prompts for approval when the compiled risk class requires it.
5. Routes approved intents to the resolved Windmill workflow path.

### Error handling

Compilation errors are explicit. `PARSE_ERROR` paths return a clean CLI error message and write a rejection event with the raw input, reason, and compiler metadata to the ledger.

## Consequences

**Positive**

- Every action is reviewable before execution as a diff-able YAML intent document.
- Risk classification and approval gating happen at compile time instead of being hidden in playbooks.
- The rule table is the single place to maintain natural-language to action mappings.
- Parse failures become auditable ledger events instead of disappearing into shell history.

**Negative / Trade-offs**

- Novel instructions are rejected until a matching rule exists.
- The alias and rule tables now require ongoing maintenance as the platform surface grows.
- The compiler adds a small amount of latency to every `lv3 run` invocation.

## Boundaries

- The goal compiler is CPU-only and deterministic for identical inputs and rule tables.
- It does not execute mutations directly; it compiles intent and resolves the workflow route.
- World-state binding is best-effort until ADR 0113 is implemented, so host and VM scope can fall back to repo-grounded defaults.

## Implementation Notes

- The compiler lives under `platform/goal_compiler/` and is loaded by the CLI through a repo-local module loader so the repository can keep the `platform/...` ADR path without colliding with Python's standard-library `platform` module.
- Intent lifecycle events are written to the current `platform/ledger/writer.py`, which now supports a repo-local fallback sink under `.local/state/ledger/ledger.events.jsonl` when no ledger DSN is configured.
- `platform/world_state/client.py` falls back to repo-local snapshots for scope binding when the DB-backed world-state materializer is not configured.

## Related ADRs

- ADR 0048: Command catalog (source of canonical action verb definitions)
- ADR 0069: Agent tool registry (source of allowed tool IDs)
- ADR 0071: Agent observation loop (all agent actions pass through the compiler)
- ADR 0080: Maintenance windows (compiler injects maintenance checks)
- ADR 0090: Platform CLI (user-facing entry point for compiled intents)
- ADR 0113: World-state materializer (future authoritative scope-binding context)
- ADR 0115: Event-sourced mutation ledger (target lifecycle model for intent events)
- ADR 0119: Budgeted workflow scheduler (future post-compiler execution stage)
