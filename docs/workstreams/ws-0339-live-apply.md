# Workstream ws-0339-live-apply: ADR 0339 Reference Deployment Samples

- ADR: [ADR 0339](../adr/0339-reference-deployment-samples-and-replaceable-provider-profiles.md)
- Title: reference deployment samples and replaceable provider profiles
- Status: live_applied
- Included In Repo Version: 0.178.4
- Branch-Local Receipt: `receipts/live-applies/2026-04-04-adr-0339-reference-deployment-samples-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-04-adr-0339-reference-deployment-samples-mainline-live-apply.json`
- Implemented On: 2026-04-04
- Live Applied On: 2026-04-04
- Live Applied In Platform Version: N/A (repo-only onboarding and automation change)
- Latest Verified Base: `origin/main@c48bdae01f6fe4d0df004e247baa8a3d9f6e013b` (`repo 0.178.3`, `platform 0.130.98`)
- Branch: `codex/ws-0339-live-apply`
- Worktree: `.worktrees/ws-0339-live-apply`
- Owner: codex
- Depends On: `ADR 0168`, `ADR 0327`, `ADR 0333`, `ADR 0334`, `ADR 0339`
- Conflicts With: none

## Scope

- add a first-class `reference-deployments/` source tree with renderable sample inventory, publication, and private overlay starter files
- add replaceable example provider profiles under `config/reference-provider-profiles.yaml`
- add a repo-managed render and validation helper so the samples stay executable instead of drifting into stale docs
- wire the new sources into discovery generation, onboarding packs, and the repository data-model gate
- record live-apply evidence for the repo automation and exact-main integration path

## Outcome

- `reference-deployments/` now carries a governed sample catalog, provider-specific starter files, and placeholder-validated templates instead of leaving fork bootstrap examples buried across unrelated docs.
- `config/reference-provider-profiles.yaml` now centralizes replaceable provider values so a new fork can render safe example inventory, publication, and local-overlay inputs from one catalog.
- `scripts/reference_deployment_samples.py` now validates the sample sources and renders bootstrap material for a selected sample/profile pair, while `scripts/validate_repository_data_models.py` enforces that those sources stay schema-correct and renderable in CI.
- discovery sources, generated onboarding packs, and validation guidance now expose the new fork-bootstrap path directly so another agent or operator can find it without reverse-engineering the repository.

## Verification

- `uv run --with pyyaml python3 scripts/reference_deployment_samples.py validate` passed on the rebased `origin/main@c48bdae01f6fe4d0df004e247baa8a3d9f6e013b` tree and is preserved in `receipts/live-applies/evidence/2026-04-04-ws-0339-reference-samples-validate-r2-0.178.3.txt`.
- `uv run --with pytest --with pyyaml python3 -m pytest -q tests/test_reference_deployment_samples.py tests/test_generate_discovery_artifacts.py` passed and is preserved in `receipts/live-applies/evidence/2026-04-04-ws-0339-targeted-tests-r2-0.178.3.txt`.
- `uv run --with pyyaml python3 scripts/reference_deployment_samples.py render --sample single-node-proxmox-lab --profile dedicated-public-edge --output-dir /tmp/ws-0339-render-check-c48` produced a concrete sample tree, and `uv tool run --from ansible-core ansible-inventory -i /tmp/ws-0339-render-check-c48/inventory/hosts.yml --list` successfully loaded the rendered inventory; both artifacts are preserved in `receipts/live-applies/evidence/2026-04-04-ws-0339-render-r2-0.178.3.txt` and `receipts/live-applies/evidence/2026-04-04-ws-0339-rendered-inventory-r2-0.178.3.json`.
- `./scripts/validate_repo.sh workstream-surfaces` and `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models` both passed after regenerating the rebased `workstreams.yaml` compatibility surface, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0339-workstream-surfaces-r2-0.178.3.txt` and `receipts/live-applies/evidence/2026-04-04-ws-0339-validate-repo-r4-0.178.3.txt`.
- The rebased release-readiness snapshot still showed repo version `0.178.3`, platform version `0.130.98`, next candidate version `0.178.4`, and unrelated waiver blockers open through `2026-04-06`, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0339-release-status-r2-0.178.3.json` and `receipts/live-applies/evidence/2026-04-04-ws-0339-release-dry-run-r2-0.178.3.txt`.

## Exact-Main Integration Status

- Exact-main release `0.178.4` now carries ADR 0339 from `origin/main@c48bdae01f6fe4d0df004e247baa8a3d9f6e013b`, with the canonical mainline receipt `receipts/live-applies/2026-04-04-adr-0339-reference-deployment-samples-mainline-live-apply.json`.
- The protected canonical-truth and release-management surfaces were refreshed from the exact-main release tree rather than through branch-local hand edits, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0339-mainline-release-lower-level-r2-0.178.4.txt`.
- Repository release `0.178.4` now includes ADR 0339 while the platform version context remains `0.130.98` because this is a repo-only onboarding and automation change.

## Notes

- ADR 0339 is a repo-only control-plane change. The target platform version remains `N/A` even after live verification because the change affects fork bootstrap assets, validation, and onboarding rather than a running service on the current deployment.
- The protected integration files (`VERSION`, release sections in `changelog.md`, the top-level `README.md` status summary, and `versions/stack.yaml`) stay untouched on this workstream branch unless the work reaches the final verified `main` integration step.
