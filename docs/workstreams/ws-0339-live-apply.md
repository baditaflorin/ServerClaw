# Workstream ws-0339-live-apply: ADR 0339 Reference Deployment Samples

- ADR: [ADR 0339](../adr/0339-reference-deployment-samples-and-replaceable-provider-profiles.md)
- Title: reference deployment samples and replaceable provider profiles
- Status: live_applied
- Included In Repo Version: not yet
- Branch-Local Receipt: `receipts/live-applies/2026-04-04-adr-0339-reference-deployment-samples-live-apply.json`
- Mainline Receipt: pending
- Implemented On: 2026-04-04
- Live Applied On: 2026-04-04
- Live Applied In Platform Version: N/A (repo-only onboarding and automation change)
- Latest Verified Base: `origin/main@20a66bbf0` (`repo 0.178.3`, `platform 0.130.98`)
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

- `uv run --with pyyaml python3 scripts/reference_deployment_samples.py validate` passed and is preserved in `receipts/live-applies/evidence/2026-04-04-ws-0339-reference-samples-validate-r1-0.178.3.txt`.
- `uv run --with pytest --with pyyaml python3 -m pytest -q tests/test_reference_deployment_samples.py tests/test_generate_discovery_artifacts.py` passed and is preserved in `receipts/live-applies/evidence/2026-04-04-ws-0339-targeted-tests-r1-0.178.3.txt`.
- `uv run --with pyyaml python3 scripts/reference_deployment_samples.py render --sample single-node-proxmox-lab --profile dedicated-public-edge --output-dir /tmp/ws-0339-render-check` produced a concrete sample tree, and `uv tool run --from ansible-core ansible-inventory -i /tmp/ws-0339-render-check/inventory/hosts.yml --list` successfully loaded the rendered inventory; both artifacts are preserved in `receipts/live-applies/evidence/2026-04-04-ws-0339-render-r1-0.178.3.txt` and `receipts/live-applies/evidence/2026-04-04-ws-0339-rendered-inventory-r1-0.178.3.json`.
- `./scripts/validate_repo.sh workstream-surfaces`, `python3 scripts/generate_diagrams.py --check`, and `./scripts/validate_repo.sh workstream-surfaces agent-standards data-models` all passed on the corrected branch-local tree after the ADR shard ownership and diagram refresh repair, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0339-workstream-surfaces-r1-0.178.3.txt` and `receipts/live-applies/evidence/2026-04-04-ws-0339-validate-repo-r3-0.178.3.txt`.
- The first promotion-facing `make pre-push-gate` replay surfaced two branch-local correction items and one expected integration-only stop: ADR shard ownership needed to declare the generated `docs/adr/index/*` surfaces, `docs/diagrams/agent-coordination-map.excalidraw` needed regeneration after the status promotion, and `generated-docs` correctly refused to proceed while `changelog.md` remained intentionally stale until exact-main canonical-truth assembly. That replay is preserved in `receipts/live-applies/evidence/2026-04-04-ws-0339-pre-push-gate-r1-0.178.3.txt`.
- The release-readiness snapshot on this branch confirms repo version `0.178.3`, platform version `0.130.98`, and that the next candidate release remains `0.178.4` while unrelated waiver blockers stay open through `2026-04-06`.

## Exact-Main Integration Status

- Branch-local proof is complete. The remaining integration step is to fast-forward the final validated branch onto the freshest `origin/main`, cut the first repo version that contains ADR 0339, write the canonical mainline receipt, and refresh any protected canonical-truth surfaces that the release cut changes.

## Notes

- ADR 0339 is a repo-only control-plane change. The target platform version remains `N/A` even after live verification because the change affects fork bootstrap assets, validation, and onboarding rather than a running service on the current deployment.
- The protected integration files (`VERSION`, release sections in `changelog.md`, the top-level `README.md` status summary, and `versions/stack.yaml`) stay untouched on this workstream branch unless the work reaches the final verified `main` integration step.
