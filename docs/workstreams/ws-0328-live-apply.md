# Workstream ws-0328-live-apply: ADR 0328 Root Summary Rollover

- ADR: [ADR 0328](../adr/0328-size-budgeted-root-summaries-and-automatic-rollover-ledgers.md)
- Title: implement size-budgeted root summaries and automatic rollover ledgers
- Status: live_applied
- Included In Repo Version: not yet
- Branch-Local Receipt: `receipts/live-applies/2026-04-03-adr-0328-root-summary-rollover-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-03-adr-0328-root-summary-rollover-mainline-live-apply.json`
- Implemented On: 2026-04-03
- Live Applied On: 2026-04-03
- Live Applied In Platform Version: not applicable (repo-only control-plane change)
- Latest Verified Base: `origin/main@9badfab73d2c7e6660bfee1287fe18c5a371614a` (`repo 0.178.3`, `platform 0.130.98`)
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

- Focused regression coverage passed: `uv run --with pytest --with pyyaml python -m pytest tests/test_root_summary.py tests/test_generate_release_notes.py tests/test_generate_status_docs.py tests/test_release_manager.py tests/test_canonical_truth.py -q` returned `22 passed in 0.57s`, preserved in `receipts/live-applies/evidence/2026-04-03-ws-0328-targeted-tests-r1-0.178.3.txt`.
- Repository automation validation passed after the workstream manifest and generated-surface refreshes: `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models generated-docs generated-portals`, preserved in `receipts/live-applies/evidence/2026-04-03-ws-0328-validate-repo-r5-0.178.3.txt`.
- Release bookkeeping proof is recorded in `receipts/live-applies/evidence/2026-04-03-ws-0328-release-status-r1.json` and `receipts/live-applies/evidence/2026-04-03-ws-0328-release-dry-run-r1-0.178.3.txt`: current repo version `0.178.3`, next candidate version `0.178.4`, `Unreleased notes: 0`, and a fresh release cut still blocked by pre-existing `controller_dependency_gap` waiver receipts plus this workstream before its status was promoted from `in_progress`.
- `make remote-validate` passed end to end on the remote builder, preserved in `receipts/live-applies/evidence/2026-04-03-ws-0328-remote-validate-r1-0.178.3.txt`.
- The first `make pre-push-gate` replay surfaced a real ADR 0208 dependency-direction violation because `platform/root_summary.py` imported `controller_automation_toolkit`; the repair is preserved in `receipts/live-applies/evidence/2026-04-03-ws-0328-pre-push-gate-r1-0.178.3.txt` and the focused confirmation in `receipts/live-applies/evidence/2026-04-03-ws-0328-dependency-direction-r1-0.178.3.txt`.
- The corrected tree then passed `make pre-push-gate`, preserved in `receipts/live-applies/evidence/2026-04-03-ws-0328-pre-push-gate-r2-0.178.3.txt`.

## Exact-Main Integration Status

- `python3 scripts/workstream_registry.py --write`, `uv run --with pyyaml python3 scripts/canonical_truth.py --write`, `uv run --with pyyaml python3 scripts/canonical_truth.py --check`, `uv run --with pyyaml python3 scripts/generate_release_notes.py --write-root-summaries`, `uv run --with pyyaml python3 scripts/generate_status_docs.py --write`, `uv run --with pyyaml --with jsonschema python3 scripts/platform_manifest.py --write`, and `uv run --with pyyaml --with jsonschema python3 scripts/generate_diagrams.py --write` refreshed the protected integration surfaces from the latest `origin/main`, preserved in `receipts/live-applies/evidence/2026-04-03-ws-0328-mainline-registry-r1.txt`, `receipts/live-applies/evidence/2026-04-03-ws-0328-mainline-canonical-truth-r1.txt`, `receipts/live-applies/evidence/2026-04-03-ws-0328-mainline-canonical-truth-check-r1.txt`, and `receipts/live-applies/evidence/2026-04-03-ws-0328-mainline-generated-surfaces-r1.txt`.
- The exact-main release snapshot now reports repository version `0.178.3`, platform version `0.130.98`, and `0 workstreams in progress`; a new numbered repo release is still blocked only by the three pre-existing `controller_dependency_gap` waiver receipts through 2026-04-06, preserved in `receipts/live-applies/evidence/2026-04-03-ws-0328-mainline-release-status-r1.json`.
- `python3 scripts/live_apply_receipts.py --validate`, `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models generated-docs generated-portals`, and `make pre-push-gate` all passed on the integrated tree, preserved in `receipts/live-applies/evidence/2026-04-03-ws-0328-mainline-live-apply-receipts-r2.txt`, `receipts/live-applies/evidence/2026-04-03-ws-0328-mainline-validate-repo-r2.txt`, and `receipts/live-applies/evidence/2026-04-03-ws-0328-mainline-pre-push-gate-r1.txt`.
