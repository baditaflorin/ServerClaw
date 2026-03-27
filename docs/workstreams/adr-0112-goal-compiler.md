# Workstream ADR 0112: Deterministic Goal Compiler

- ADR: [ADR 0112](../adr/0112-deterministic-goal-compiler.md)
- Title: CPU-only rule-driven compiler that translates operator natural language into a typed, schema-validated `ExecutionIntent` before anything touches the platform
- Status: merged
- Branch: `codex/adr-0112-goal-compiler`
- Worktree: `.worktrees/adr-0112`
- Owner: codex
- Depends On: `adr-0048-command-catalog`, `adr-0069-agent-tool-registry`, `adr-0090-platform-cli`
- Conflicts With: `adr-0113-world-state-materializer` (shared `config/` surfaces), `adr-0115-mutation-ledger` (shared `platform/ledger/` module)
- Shared Surfaces: `platform/goal_compiler/`, `platform/ledger/`, `platform/world_state/`, `config/goal-compiler-rules.yaml`, `config/goal-compiler-aliases.yaml`, `scripts/lv3_cli.py`

## Delivered Scope

- added `platform/goal_compiler/schema.py` with `ExecutionIntent`, `IntentTarget`, `IntentScope`, `RiskClass`, and `RiskScore`
- added `platform/goal_compiler/rules.py` and `platform/goal_compiler/compiler.py` with deterministic normalisation, ordered rule matching, and scope/precondition injection
- added `config/goal-compiler-rules.yaml` with more than ten initial rules covering direct workflow runs plus `deploy`, `converge`, `rotate`, `restart`, `rollback`, `check`, `query`, and maintenance-window actions
- added `config/goal-compiler-aliases.yaml` with canonical phrase aliases and monitoring-stack group expansion
- extended the current `platform/ledger/writer.py` so `intent.compiled`, `intent.approved`, `intent.rejected`, and `intent.expired` can fall back to a repo-local JSONL sink when no ledger DSN is configured
- extended the current `platform/world_state/client.py` with repo-local snapshot fallback for best-effort scope binding when DB-backed world-state is unavailable
- updated `scripts/lv3_cli.py` so `lv3 run` preserves direct workflow execution for risk-scored workflow IDs while also compiling natural-language instructions into YAML intent summaries, prompting for approval when required, writing ledger events, and dispatching to Windmill
- added `scripts/repo_package_loader.py` so repo-local `platform/...` modules can be loaded without colliding with the stdlib `platform` module
- added `tests/unit/test_goal_compiler.py` and extended `tests/test_lv3_cli.py`
- updated `docs/runbooks/platform-cli.md` with the new `lv3 run` operator flow

## Verification

- `uv run --with pyyaml --with pytest pytest tests/unit/test_goal_compiler.py tests/test_lv3_cli.py -q`
- `uv run --with pyyaml --with pytest --with httpx --with jinja2 --with fastapi --with jsonschema --with cryptography --with itsdangerous --with qdrant-client --with python-multipart pytest -q`

## Notes For The Next Assistant

- The compiler currently routes natural-language instructions directly to Windmill after compilation. ADR 0119 should replace that final dispatch with the scheduler hand-off once the scheduler exists.
- The repo-local snapshot fallback in `platform/world_state/client.py` is only a compatibility path for ADR 0112. Do not promote it to the authoritative materializer interface when ADR 0113 evolves further.
- The `platform/...` directory is intentionally not imported via `platform.*` because Python loads the stdlib `platform` module early. Keep using the repo package loader unless the package root is renamed.
