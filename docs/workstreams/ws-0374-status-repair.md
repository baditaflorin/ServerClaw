# Workstream ws-0374-status-repair: ADR 0374 Status Artifact Repair

- ADR: [ADR 0374](../adr/0374-cross-cutting-service-manifest.md)
- Title: repair stale ADR 0374 status artifacts on the latest `origin/main`
- Status: ready_for_merge
- Branch: `codex/ws-0374-status-repair`
- Worktree: `.worktrees/ws-0374-status-repair`
- Owner: codex
- Depends On: `ws-0374-live-apply`
- Conflicts With: none

## Scope

- verify the current exact-main ADR 0374 metadata and generated status surfaces
- repair the ADR implementation scanner summary labeling so generated reports distinguish decision status from implementation status
- regenerate the ADR index and the ADR 0374 implementation-status report so `origin/main` no longer advertises ADR 0374 as proposed
- run focused repo validation from the clean exact-main worktree and merge the repair to `main`

## Verification Plan

- `python3 scripts/generate_adr_index.py --write`
- `python3 scripts/adr_implementation_scanner.py --adr-numbers 0374 --output docs/adr/implementation-status --format yaml`
- `pytest -q tests/test_adr_implementation_scanner.py tests/test_generate_adr_index.py`
- `./scripts/validate_repo.sh agent-standards`

## Verification Results

- `python3 scripts/generate_adr_index.py --write`
- `python3 scripts/adr_implementation_scanner.py --adr-numbers 0374 --output docs/adr/implementation-status --format yaml`
- `uv run --with pytest --with pyyaml pytest -q tests/test_adr_implementation_scanner.py tests/test_generate_adr_index.py`
- `./scripts/validate_repo.sh agent-standards`

Result:

- `docs/adr/index/by-status/implemented.yaml` now classifies ADR 0374 as implemented.
- `docs/adr/implementation-status/adr-0374.yaml` now records `Canonical Decision Status: Accepted`, `Canonical Implementation Status: Implemented`, and `Inferred Implementation Status: Likely Implemented`.
- The implementation scanner now treats committed live-apply receipts as implementation evidence and the ADR index parser now accepts bold ADR frontmatter keys like `- **Status**:`.
