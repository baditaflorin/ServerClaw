# Workstream ADR 0369: Python Validation Toolkit

- ADR: [ADR 0369](../adr/0369-python-validation-toolkit.md)
- Title: Replace duplicated `require_*` validators with a shared `scripts/validation_toolkit.py`
- Status: in_progress
- Branch: `codex/adr-0369-mainline`
- Worktree: `.worktrees/adr-0369-mainline`
- Owner: codex
- Depends On: `adr-0039-controller-automation-toolkit`, `adr-0048-command-catalog-pattern`
- Conflicts With: none

## Scope

- restore `scripts/validation_toolkit.py` to the exact ADR 0369 module contents
- keep `scripts/test_validation_toolkit.py` as a zero-dependency smoke test
- move non-ADR YAML identity helpers out of `validation_toolkit.py`
- migrate every current-main script that still defines local duplicated `require_*` helpers
- verify each migrated script in its own validation mode before committing
- run the full `make validate-schemas` gate once the full migration is complete

## Non-Goals

- changing protected release or mainline truth surfaces such as `VERSION`,
  `changelog.md`, `RELEASE.md`, or `README.md` before the final merge step
- changing validator behaviour beyond the canonical ADR 0369 implementations
- introducing non-stdlib dependencies or packaging `scripts/` as a Python module

## Expected Repo Surfaces

- `docs/adr/0369-python-validation-toolkit.md`
- `docs/workstreams/adr-0369-python-validation-toolkit.md`
- `scripts/validation_toolkit.py`
- `scripts/test_validation_toolkit.py`
- `scripts/identity_yaml.py`
- `scripts/generate_cross_cutting_artifacts.py`
- `scripts/generate_ops_portal.py`
- the current scripts returned by
  `git grep -l "def require_mapping\\|def require_str\\|def require_list" origin/main -- scripts/*.py`
- `workstreams/active/adr-0369-python-validation-toolkit.yaml`
- `workstreams.yaml`

## Verification

- `python scripts/test_validation_toolkit.py`
- one per-script validation command for each migrated script
- `make validate-schemas`

## Notes For The Next Assistant

- ADR 0369 requires exact function signatures, docstrings, and error message
  formats in `scripts/validation_toolkit.py`; treat that file as a copy-exact
  contract, not a design space.
- `origin/main` currently contains extra helpers in `validation_toolkit.py`;
  those must live elsewhere before the module can match the ADR again.
- Several remaining scripts use local validators for duplicate-detection or
  domain-specific parsing. Keep the domain-specific logic, but rename those
  helpers away from `require_*` when they are not canonical toolkit functions.
