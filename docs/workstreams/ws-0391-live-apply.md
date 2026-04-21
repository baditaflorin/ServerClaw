# Workstream ws-0391-live-apply

- ADR: [ADR 0391](../adr/0391-cpu-only-operational-automation.md)
- Branch: `codex/ws-0391-main-integration`
- Worktree: `.worktrees/ws-0391-main-integration`
- Owner: codex
- Status: live applied, main PR integration ready
- Source commit: `a660ea551539e848dfb91e44d07f5e43b8347c89`
- Source branch: `codex/ws-0391-live-apply`

## Purpose

Finish and live-apply ADR 0391 from the latest reachable `origin/main`, using
an isolated worktree so concurrent agents do not collide with this workstream.

## Scope

- Added the missing `platform_ops.py validation-plan` subcommand.
- Added the documented `ops-*` Make targets.
- Added focused pytest coverage for the validation planner.
- Added this runbook, workstream shard, ADR metadata, and live-apply receipt
  evidence.

## Verification

- `uv run --with pytest python -m pytest tests/test_platform_ops.py -q` passed
  with `5 passed`.
- Every `platform_ops.py` subcommand help path returned zero for:
  `references`, `impact`, `converge-plan`, `completeness`,
  `validation-plan`, `changelog`, and `decommission-preview`.
- JSON-producing checks parsed successfully for `impact`, `references`,
  `validation-plan`, `converge-plan`, `completeness`, `changelog`, and
  `decommission-preview`.
- `make ops-validation-plan` and `make ops-converge-plan` completed from
  `SINCE=origin/main`; the validation planner reported zero unmapped files.
- `python3 scripts/workstream_registry.py --check`, `uv run --with pyyaml
  python3 scripts/generate_adr_index.py --check`, `python3
  scripts/live_apply_receipts.py --validate`, `./scripts/validate_repo.sh
  agent-standards`, `./scripts/validate_repo.sh workstream-surfaces`,
  `./scripts/validate_repo.sh data-models`, `./scripts/validate_repo.sh json
  yaml`, `./scripts/validate_repo.sh python-type-safety`, `./scripts/validate_repo.sh
  semgrep`, and `git diff --check` passed.
- `./scripts/validate_repo.sh generated-docs` is deferred to main integration:
  the gate requires `changelog.md` canonical truth, and this branch is not
  allowed to update protected release sections.

## Merge-To-Main Remainder

This workstream branch intentionally does not update protected integration
files. The final main integration step must decide and apply the appropriate
release bookkeeping for:

- `VERSION`
- release sections in `changelog.md`
- generated top-level `README.md` status
- `versions/stack.yaml`

The branch-local live apply is repo/controller automation only; no host or
guest converge is required for ADR 0391.

On 2026-04-21, the release-manager path for cutting `0.178.149` was blocked by
unrelated global release blockers (`release_manager.py status` reported four
blocking workstreams plus expired waiver blockers). ADR 0391 is therefore ready
for PR integration as a feature branch, while the release cut and protected
top-level version/status surfaces remain with the next release-ready main
integration step.
