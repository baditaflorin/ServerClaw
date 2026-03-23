# Workstream ADR 0112: Deterministic Goal Compiler

- ADR: [ADR 0112](../adr/0112-deterministic-goal-compiler.md)
- Title: CPU-only rule-driven compiler that translates operator natural language into a typed, schema-validated ExecutionIntent before anything touches the platform
- Status: ready
- Branch: `codex/adr-0112-goal-compiler`
- Worktree: `../proxmox_florin_server-goal-compiler`
- Owner: codex
- Depends On: `adr-0048-command-catalog`, `adr-0069-agent-tool-registry`, `adr-0090-platform-cli`
- Conflicts With: `adr-0113-world-state-materializer` (shared `config/` surfaces), `adr-0115-mutation-ledger` (shared `platform/ledger/` module)
- Shared Surfaces: `platform/goal_compiler/`, `config/goal-compiler-rules.yaml`, `config/goal-compiler-aliases.yaml`, `platform/ledger/writer.py`

## Scope

- create `platform/goal_compiler/__init__.py` and `platform/goal_compiler/schema.py` — `ExecutionIntent` dataclass and all sub-types (`IntentTarget`, `IntentScope`, `RiskClass`, `RiskScore`)
- create `platform/goal_compiler/compiler.py` — three-stage pipeline: normalisation, rule matching, scope and precondition injection
- create `platform/goal_compiler/rules.py` — rule table loader and matcher (regex + substring pattern matching)
- create `config/goal-compiler-rules.yaml` — initial rule set covering `deploy`, `rotate`, `restart`, `query`, `rollback`, `check`, `converge` verbs
- create `config/goal-compiler-aliases.yaml` — service alias table and group expansions (e.g. "the monitoring stack" → ["grafana", "loki", "prometheus"])
- extend `platform/ledger/writer.py` — add `intent.compiled`, `intent.approved`, `intent.rejected`, `intent.expired` event types
- update `lv3 run <instruction>` CLI command (ADR 0090) — call compiler, display compiled intent as YAML, prompt for approval if `requires_approval: true`
- write `tests/unit/test_goal_compiler.py` — round-trip tests for all initial rules; parse-error tests for unrecognised instructions; scope-binding tests

## Non-Goals

- Executing anything — the compiler produces intents only; execution is the scheduler's job (ADR 0119)
- Writing the world-state client used for scope binding — that is ADR 0113's deliverable; stub it with a mock in tests
- Writing the risk scorer integration — ADR 0116 will call the compiler's output; this workstream produces the compiler only

## Expected Repo Surfaces

- `platform/goal_compiler/__init__.py`
- `platform/goal_compiler/schema.py`
- `platform/goal_compiler/compiler.py`
- `platform/goal_compiler/rules.py`
- `config/goal-compiler-rules.yaml`
- `config/goal-compiler-aliases.yaml`
- `platform/ledger/writer.py` (patched: intent event types added)
- `docs/adr/0112-deterministic-goal-compiler.md`
- `docs/workstreams/adr-0112-goal-compiler.md`

## Expected Live Surfaces

- `lv3 run "deploy netbox"` compiles successfully and displays the intent YAML before executing
- `lv3 run "some unrecognised free text"` returns a `PARSE_ERROR` message, not a traceback
- All intent lifecycle events appear in the mutation ledger after a successful `lv3 run` invocation

## Verification

- Run `pytest tests/unit/test_goal_compiler.py -v` → all tests pass
- Run `lv3 run "deploy netbox" --dry-run` on the controller → inspect the compiled intent YAML output
- Confirm a `intent.compiled` event appears in `ledger.events` after the dry-run
- Introduce a deliberate typo instruction (`lv3 run "dploy netbox"`) → confirm `PARSE_ERROR` output with no platform mutation

## Merge Criteria

- All unit tests pass
- `lv3 run` interactive flow compiles, displays intent, and routes to Windmill on confirmation
- `PARSE_ERROR` path tested manually on the controller
- At least 10 rules in the initial `goal-compiler-rules.yaml` covering the most common operator verbs

## Notes For The Next Assistant

- The `scope_binding` step in the compiler needs a world-state client. Until ADR 0113 is implemented, the compiler should call `WorldStateClient().get("proxmox_vms", allow_stale=True)` and gracefully handle a connection failure by leaving `scope.allowed_hosts` as the raw rule-table default rather than raising an exception
- The rule table uses first-match semantics; the order of rules in `goal-compiler-rules.yaml` matters — more specific patterns must appear before more general ones
- Intent IDs are UUIDs generated at compile time, not at execution time. This means retrying a failed execution should re-compile to get a fresh intent ID, not reuse the old one
- The `ttl_seconds` field defaults to 300 (5 minutes). The scheduler (ADR 0119) should reject intents whose `created_at + ttl_seconds < now()`
