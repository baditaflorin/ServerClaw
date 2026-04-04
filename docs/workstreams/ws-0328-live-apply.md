# Workstream ws-0328-live-apply: ADR 0328 Root Summary Rollover

- ADR: [ADR 0328](../adr/0328-size-budgeted-root-summaries-and-automatic-rollover-ledgers.md)
- Title: implement size-budgeted root summaries and automatic rollover ledgers
- Status: live_applied
- Included In Repo Version: 0.178.4
- Branch-Local Receipt: `receipts/live-applies/2026-04-03-adr-0328-root-summary-rollover-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-03-adr-0328-root-summary-rollover-mainline-live-apply.json`
- Implemented On: 2026-04-03
- Live Applied On: 2026-04-03
- Live Applied In Platform Version: not applicable (repo-only control-plane change)
- Latest Verified Base: `origin/main@442e640cfd8895b645dd1e7b66977f1701260e07` (`repo 0.178.3`, `platform 0.130.98`)
- Branch: `codex/ws-0328-live-apply`
- Worktree: `.worktrees/ws-0328-live-apply`
- Owner: codex
- Depends On: `ADR 0038`, `ADR 0081`, `ADR 0167`, `ADR 0174`
- Conflicts With: none

## Scope

- add an explicit repo-managed budget policy for root summary surfaces
- keep `README.md`, `changelog.md`, and `docs/release-notes/README.md` bounded even as release and workstream history grows
- generate deeper archive ledgers under `docs/release-notes/index/` and `docs/status/history/`
- teach the validation and release paths to regenerate and enforce those surfaces automatically

## Outcome

- `config/root-summary-budgets.yaml` now declares explicit line and entry budgets for the root README, changelog, and release-note index surfaces.
- `platform/root_summary.py` now centralizes budget loading, root-summary line enforcement, release-note archive grouping, and README history collection so the generators can share one rollover policy.
- `scripts/generate_release_notes.py`, `scripts/generate_status_docs.py`, `scripts/release_manager.py`, `scripts/validate_repo.sh`, and `Makefile` now regenerate or validate the bounded root-summary surfaces as part of normal repo automation instead of relying on one-off manual cleanup.
- `README.md`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/index/*.md`, and `docs/status/history/*.md` are now generated from that policy so the root entrypoints stay compact while older release and workstream history rolls into deeper ledgers.

## Verification

- Focused regression coverage passed on the rebased exact-main tree: `uv run --with pytest --with pyyaml python -m pytest tests/test_root_summary.py tests/test_generate_release_notes.py tests/test_generate_status_docs.py tests/test_release_manager.py tests/test_canonical_truth.py -q` returned `22 passed in 0.77s`, preserved in `receipts/live-applies/evidence/2026-04-03-ws-0328-targeted-tests-r2-0.178.3.txt`.
- Repository automation validation passed after the workstream manifest and generated-surface refreshes: `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models generated-docs generated-portals`, preserved in `receipts/live-applies/evidence/2026-04-03-ws-0328-validate-repo-r5-0.178.3.txt`.
- Release bookkeeping proof is recorded in `receipts/live-applies/evidence/2026-04-03-ws-0328-release-status-r1.json` and `receipts/live-applies/evidence/2026-04-03-ws-0328-release-dry-run-r1-0.178.3.txt`: current repo version `0.178.3`, next candidate version `0.178.4`, `Unreleased notes: 0`, and a fresh release cut still blocked by pre-existing `controller_dependency_gap` waiver receipts plus this workstream before its status was promoted from `in_progress`.
- `make remote-validate` passed end to end on the rebased exact-main tree, preserved in `receipts/live-applies/evidence/2026-04-03-ws-0328-mainline-remote-validate-r2.txt`.
- The first `make pre-push-gate` replay surfaced a real ADR 0208 dependency-direction violation because `platform/root_summary.py` imported `controller_automation_toolkit`; the repair is preserved in `receipts/live-applies/evidence/2026-04-03-ws-0328-pre-push-gate-r1-0.178.3.txt` and the focused confirmation in `receipts/live-applies/evidence/2026-04-03-ws-0328-dependency-direction-r1-0.178.3.txt`.
- The corrected tree then passed `make pre-push-gate` on the rebased exact-main tree, with a final confirmation rerun preserved in `receipts/live-applies/evidence/2026-04-03-ws-0328-mainline-pre-push-gate-r4.txt`.

## Exact-Main Integration Status

- ADR 0328's bounded-summary and rollover surfaces are now part of repository release `0.178.4`.
- Repository release `0.178.4` preserves the exact-main generator evidence while recording ADR 0328 in `VERSION`, `RELEASE.md`, `changelog.md`, `README.md`, `versions/stack.yaml`, and the generated release-note plus status-history surfaces.
- ADR 0328 is a repo-only control-plane change, so the platform version context remains `0.130.98`.
