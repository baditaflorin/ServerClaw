# ws-0369-live-apply — ADR 0369 exact-main completion

## Goal

Close the remaining ADR 0369 gaps on top of the latest `origin/main`, then
record exact-main validation and live-apply evidence so the work can merge
safely without guessing about implementation status.

## Gaps found at start

- `scripts/validation_toolkit.py` and its tests already existed on `origin/main`.
- The ADR text claimed 100% migration complete, but multiple scripts still
  redefined toolkit validator names such as `require_mapping`,
  `require_string_list`, `require_identifier`, `require_enum`, and
  `require_http_url`.
- `scripts/enforce_validation_toolkit.sh` only checked whether a file imported
  `validation_toolkit`; it did not fail when the same file still redefined the
  canonical validator names locally.
- Generated ADR implementation-status artifacts still classified ADR 0369 as
  proposed despite strong implementation evidence in git history.

## Completion criteria

- remaining canonical validator redefinitions removed or renamed to clearly
  domain-specific helpers
- enforcement updated so new duplicate validator definitions fail closed
- toolkit validation/tests and repo validation paths re-run from this worktree
- live-apply evidence written under `receipts/live-applies/`
- ADR metadata updated with verified implementation status and merge-to-main
  follow-up notes where protected integration files must wait

## Exact-Main Verification

- Latest base verified in this session: `origin/main@e0134a1fe` (`2026-04-14 18:25:58 +0300`, repo `VERSION` `0.178.141`)
- Repo-only live-apply scope: no host or guest automation was executed; the apply consisted of exact-main repository validation and governance checks from the dedicated worktree

### Validation evidence

- `python3 scripts/test_validation_toolkit.py`
  - passed
- `uv run --with pytest --with pyyaml pytest tests/test_validation_toolkit_contract.py tests/test_validate_repo_cache.py -q`
  - passed
- `bash scripts/enforce_validation_toolkit.sh --all-files`
  - passed
- `./scripts/validate_repo.sh data-models agent-standards`
  - passed on the latest rebased worktree after materializing the fresh-worktree generated inputs with `make generate-platform-vars`
  - non-blocking note emitted by the wrapper: `WARNING: Branch 'codex/ws-0369-main-integration-final' not found in workstreams.yaml (ADR 0167)`

### Exact-main fixes closed here

- migrated the last canonical validator holdouts to `scripts/validation_toolkit.py`
- fixed the `set -e` bookkeeping bug in `scripts/validate_repo.sh` so the combined wrapper reports real downstream failures instead of exiting silently
- added `tests/test_validation_toolkit_contract.py` to keep duplicate canonical validator definitions from re-entering the repo
- regenerated the fresh-worktree cross-cutting artifacts and `inventory/group_vars/platform.yml`, then refreshed `scripts/topology-snapshot.json` so the final exact-main validation ran against the same governed generated inputs as `main`
- after rebasing to the latest `origin/main`, restored the `AGENTS.md` public-entrypoint reference to the generic `inventory/host_vars/<topology-host>.yml` form so the merged tree still passed the public-surface validation gate

## Mainline Closeout

Merged on top of the latest reachable `origin/main` and included in repo `VERSION` `0.178.142`.

- archived workstream record: `workstreams/archive/2026/ws-0369-live-apply.yaml`
- exact-main receipt: `receipts/live-applies/2026-04-14-adr-0369-python-validation-toolkit-mainline-live-apply.json`
- live-apply scope remained repo-only; no host or guest automation changed during this closeout
