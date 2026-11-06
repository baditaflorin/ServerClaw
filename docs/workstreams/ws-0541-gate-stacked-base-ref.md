# WS-0541: Pre-push gate for a branch stacked on an unmerged branch

## Status

In progress. The pull request is open and not merged; nothing is applied. No `[live-apply]` marker.

## Goal

The pre-push gate compared every branch with `origin/main`: `scripts/remote_exec.sh` built the changed-file list and exported the base ref from it, and `scripts/validate_repo.sh` passed `origin/main` to `workstream_surface_ownership.py --validate-branch`. A branch stacked on an unmerged parent therefore carried the parent's files and failed `workstream-surfaces` on every builder, after which the pre-push hook fell back to a local run on the laptop. This change lets the caller name the parent as the base.

## Change

- `scripts/remote_exec.sh` (`compute_validation_lane_context`): a `LV3_VALIDATION_BASE_REF` set by the caller is kept, and the changed files are computed against it. A ref that does not resolve to a commit stops the run with an error naming it, because the diff would otherwise print `[]` and an empty change list passes every surface check. Unset, the base is chosen as before (`origin/main`, or `main` when that ref is missing).
- `scripts/validate_repo.sh` (`validate_workstream_surfaces`): `--base-ref "${LV3_VALIDATION_BASE_REF:-origin/main}"`. `renovate_stack_digest_guard` stays on `origin/main` on purpose: it checks that the stack version and the image-catalog digest changed together over everything that will land on main, and a parent that is internally consistent never makes a stacked branch fail it, while a parent ref as base could (a child that finishes a bump the parent started).
- Tests: `tests/test_remote_exec.py` (a throwaway main - parent - child repo: default base and the cumulative change list, a kept caller base and the child-only change list, an unresolvable base refused), `tests/test_validate_repo_cache.py` (the real stage with a recording package runner: default `origin/main`, the variable passed through), `tests/test_workstream_surface_ownership.py` (a stacked branch fails against `main` and passes against its parent, by function and by command line).
- `docs/runbooks/validation-gate.md`: a short Stacked Branches section, including the rebase after the parent merges (`git rebase --onto origin/main <parent head> <child>`) and that the child's shard lists the parent in `depends_on`.

## Not changed

Behaviour with the variable unset. Semgrep (`scripts/semgrep_gate.py --baseline-ref`) already reads the variable, so on a checkout that has git history its baseline is the parent too; the build-server snapshot carries no git metadata, so there it is skipped as before.
