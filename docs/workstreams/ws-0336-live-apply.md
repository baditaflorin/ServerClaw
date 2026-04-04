# Workstream ws-0336-live-apply: ADR 0336 Public Entrypoint Leakage Validation

- ADR: [ADR 0336](../adr/0336-public-entrypoint-leakage-validation.md)
- Title: verify ADR 0336 public entrypoint leakage validation on the latest origin/main
- Status: merged
- Included In Repo Version: not yet
- Branch-Local Receipt: `receipts/live-applies/2026-04-04-adr-0336-public-entrypoint-leakage-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-04-adr-0336-public-entrypoint-leakage-mainline-live-apply.json`
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-04
- Live Applied In Platform Version: not applicable (repo-only control-plane validation)
- Latest Verified Base: `origin/main@61900f1de988da19bc4db1fde27fa54e0e5aabb1` (`repo 0.178.3`, `platform 0.130.98`)
- Branch: `codex/ws-0336-live-apply`
- Worktree: `.worktrees/ws-0336-live-apply`
- Owner: codex
- Depends On: `ADR 0168`, `ADR 0330`, `ADR 0336`
- Conflicts With: none

## Scope

- verify that the committed public-entrypoint validator and its gate integration are still present and green on the latest realistic `origin/main`
- record branch-local and exact-main evidence without pretending this repo-only ADR required a new platform mutation
- register the workstream in the shard-backed registry so agent-standards and surface-ownership checks can validate the branch itself

## Outcome

- The validator implementation was already present on exact `origin/main` at `61900f1de988da19bc4db1fde27fa54e0e5aabb1`; no code change to `scripts/validate_public_entrypoints.py` or the gate wiring was required for ADR 0336 itself.
- This workstream adds explicit verification evidence, a dedicated workstream record, and a small ADR metadata clarification that the platform-version field is not applicable because the change is repository-only.
- Protected integration files remain untouched on the workstream branch: no `VERSION` bump, no release-section churn in `changelog.md`, no top-level README status rewrite, and no `versions/stack.yaml` edit.

## Verification

- `python3 scripts/validate_public_entrypoints.py --check` passed on the exact-main worktree, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0336-validate-public-entrypoints-r1.txt`.
- Focused regression coverage passed on the exact-main worktree: `uv run --with pytest --with pyyaml python3 -m pytest -q tests/test_validate_public_entrypoints.py tests/test_validate_repo_cache.py tests/test_generate_discovery_artifacts.py` returned `29 passed in 2.04s`, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0336-targeted-tests-r1.txt`.
- The rebased exact-main tree passed `./scripts/validate_repo.sh agent-standards generated-docs`, `uv run --with jsonschema python3 scripts/validate_repository_data_models.py --validate`, `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate`, and `git diff --check`, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0336-mainline-validate-repo-r1.txt`, `receipts/live-applies/evidence/2026-04-04-ws-0336-data-models-r1.txt`, `receipts/live-applies/evidence/2026-04-04-ws-0336-mainline-live-apply-receipts-r1.txt`, and `receipts/live-applies/evidence/2026-04-04-ws-0336-mainline-git-diff-check-r1.txt`. The archived terminal-history tree now fails `./scripts/validate_repo.sh agent-standards workstream-surfaces generated-docs` only because `ws-0336` is no longer present in the active registry, and that expected ownership failure is preserved in `receipts/live-applies/evidence/2026-04-04-ws-0336-validate-repo-r4.txt`.
- `make remote-validate` exercised the remote-wrapper path end to end: the remote command failed, the wrapper fell back locally, and the fallback runner passed `agent-standards`, `alert-rule-validation`, `ansible-syntax`, `atlas-lint`, `dependency-graph`, `iac-policy-scan`, `policy-validation`, `schema-validation`, and `type-check`. The only remaining failure was `workstream-surfaces`, because the branch now maps to terminal archived history instead of an active registry entry. That result is preserved verbatim in `receipts/live-applies/evidence/2026-04-04-ws-0336-remote-validate-r1.txt`.
- The promotion-facing `make pre-push-gate` replay is performed from detached `HEAD` on the finished archive commit so the gate does not incorrectly select the terminal `codex/ws-0336-live-apply` branch for active-branch ownership validation.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python3 scripts/release_manager.py status --json` reports repository version `0.178.3`, platform version `0.130.98`, `0 workstreams in progress`, and a blocked release cut only because three unrelated `controller_dependency_gap` waivers remain open through `2026-04-06`, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0336-release-status-r1.json`.

## Exact-Main Integration Status

- The validator already ships on `origin/main`; this workstream exists to make that state auditable from a dedicated branch/worktree even after `origin/main` advanced to `61900f1de988da19bc4db1fde27fa54e0e5aabb1`.
- The branch-local closeout completed on `codex/ws-0336-live-apply`, and the mainline closeout archives the workstream as terminal history so the registry no longer carries it as active.
- Because another local worktree already owns a dirty `main` branch, the exact-main push for this workstream is performed by pushing the verified integration commit directly to `origin/main` instead of mutating that unrelated local `main` checkout.
