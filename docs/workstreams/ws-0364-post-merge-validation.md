# Workstream ws-0364-post-merge-validation

- ADR: [ADR 0364](../adr/0364-native-build-server-gate-execution.md)
- Status: merged
- Branch: `codex/ws-0364-post-merge-validation-r2`
- Worktree: `.worktrees/ws-0364-post-merge-validation`
- Base: `origin/main@0ed784c50` (`VERSION` `0.178.135`)

## Purpose

Close the remaining validation and integration loop after the ADR 0364 live apply by rerunning the build-server automation from the newest realistic `origin/main`, repairing repo-local gate regressions, and recording the resulting proof chain in git-visible state.

## Current Focus

- revalidate `check-build-server` from this isolated worktree
- rerun `remote-validate` and its governed local fallback path
- repair gate blockers surfaced by current-main drift so the validation bundle can pass cleanly
- leave workstream metadata explicit so another agent could continue without hidden chat context if interrupted

## Verification

- `make check-build-server` passed from this worktree on 2026-04-14 against `origin/main@0ed784c50`.
- `make remote-validate` completed on 2026-04-14 through the governed local fallback path after the remote build server reported runner image pull failures for `registry.example.com`; the fallback passed `workstream-surfaces`, `agent-standards`, `ansible-syntax`, `schema-validation`, `atlas-lint`, `policy-validation`, `iac-policy-scan`, `alert-rule-validation`, `type-check`, and `dependency-graph`.
- `./scripts/run_python_with_packages.sh jsonschema pyyaml pytest -- -m pytest tests/test_parallel_check.py tests/test_run_gate_fallback.py tests/test_validation_gate.py tests/test_remote_exec.py tests/test_ansible_execution_scopes.py tests/test_repo_intake_runtime_role.py tests/test_validate_service_completeness.py -q` passed with `69 passed`.
