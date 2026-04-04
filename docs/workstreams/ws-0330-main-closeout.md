# Workstream ws-0330-main-closeout: Close Out ADR 0330 On The Latest `origin/main`

- ADR: [ADR 0330](../adr/0330-public-github-readiness-as-a-first-class-repository-lifecycle.md)
- Title: verify and close out public GitHub readiness on the exact-main tree
- Status: live_applied
- Included In Repo Version: `not yet`
- Branch-Local Receipt: `receipts/live-applies/2026-04-04-adr-0330-public-github-readiness-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-04-adr-0330-public-github-readiness-mainline-live-apply.json`
- Implemented On: 2026-04-04
- Live Applied On: 2026-04-04
- Live Applied In Platform Version: `not applicable (repo-only control-plane change)`
- Latest Verified Base: `origin/main@20a66bbf088d1aa456d34f173fd8e2c8664f4c20` (`repo 0.178.3`, `platform 0.130.98`)
- Branch: `codex/ws-0330-main-closeout`
- Worktree: `.worktrees/ws-0330-main-closeout`
- Owner: codex
- Depends On: `ADR 0163`, `ADR 0166`, `ADR 0168`, `ADR 0330`, `ADR 0333`, `ADR 0334`, `ADR 0338`, `ADR 0339`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `workstreams/active/ws-0330-main-closeout.yaml`, `docs/workstreams/ws-0330-main-closeout.md`, `docs/adr/0330-public-github-readiness-as-a-first-class-repository-lifecycle.md`, `docs/adr/0333-private-overlay-files-for-deployment-specific-secrets-and-identities.md`, `docs/adr/0334-example-first-inventory-and-service-identity-catalogs.md`, `docs/adr/0338-public-documentation-tiers-and-private-history-boundaries.md`, `docs/adr/0339-reference-deployment-samples-and-replaceable-provider-profiles.md`, `docs/adr/.index.yaml`, `docs/adr/index/by-range/*.yaml`, `docs/adr/index/by-concern/*.yaml`, `docs/adr/index/by-status/*.yaml`, `docs/reference-deployments/README.md`, `docs/runbooks/controller-local-secrets-and-preflight.md`, `docs/runbooks/fork-reference-platform.md`, `docs/runbooks/validate-repository-automation.md`, `docs/discovery/repo-structure/documentation-and-history.yaml`, `docs/discovery/repo-structure/automation-and-infrastructure.yaml`, `docs/discovery/config-locations/inventory.yaml`, `docs/discovery/config-locations/automation.yaml`, `.repo-structure.yaml`, `.config-locations.yaml`, `build/onboarding/**`, `README.md`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/index/*.md`, `docs/status/history/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`, `config/controller-local-secrets.json`, `config/examples/**`, `inventory/examples/reference-platform/**`, `platform/repo.py`, `platform/agent/coordination.py`, `platform/maintenance/windows.py`, `scripts/controller_automation_toolkit.py`, `scripts/drift_lib.py`, `scripts/intent_queue_dispatcher.py`, `scripts/ntfy_publish.py`, `scripts/uptime_robot_tool.py`, `scripts/seed_data_snapshots.py`, `scripts/topology-snapshot.json`, `tests/test_config_merge_windmill.py`, `tests/test_controller_automation_toolkit.py`, `tests/test_ntfy_publish.py`, `tests/test_public_reference_samples.py`, `receipts/live-applies/2026-04-04-adr-0330-public-github-readiness-live-apply.json`, `receipts/live-applies/2026-04-04-adr-0330-public-github-readiness-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-04-ws-0330-*`

## Scope

- finish the repo-relative `.local/...` controller-secret contract so the committed manifest no longer leaks one workstation root
- add fork-first example inventory, publication, provider, and controller-overlay surfaces
- place those samples into an explicit public reference documentation tier
- regenerate the discovery entrypoints and onboarding packs so the new fork-first surfaces show up in the public onboarding path
- verify the exact-main tree through focused tests plus the broader repository validation and push gates

## Non-Goals

- changing the live platform topology
- bumping `VERSION` or cutting a release
- rewriting historical receipts or unrelated runbooks outside the ADR 0330 closeout scope

## Verification

- `python3 scripts/workstream_registry.py --write`
- `uv run --with pyyaml python3 scripts/generate_discovery_artifacts.py --write`
- `uv run --with pyyaml python3 scripts/generate_adr_index.py --write`
- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_controller_automation_toolkit.py tests/test_config_merge_windmill.py tests/test_ntfy_publish.py tests/test_public_reference_samples.py`
- `./scripts/validate_repo.sh agent-standards workstream-surfaces`
- `./scripts/validate_repo.sh agent-standards workstream-surfaces generated-docs` on the protected exact-main integration tree
- `python3 scripts/live_apply_receipts.py --validate`
- `make validate`
- `make remote-validate`
- `make pre-push-gate`
- `git diff --check`

## Notes

- The branch-local phase intentionally left `README.md`, `changelog.md`, and `versions/stack.yaml` untouched until the protected exact-main integration step; the final exact-main replay then refreshed those surfaces plus the status ledgers, platform manifest, and coordination diagram from workstream canonical truth.
- The first exact-main `make remote-validate` replay surfaced a duplicate `resolve_repo_local_path` definition in `scripts/controller_automation_toolkit.py`, and the first post-fix `validate_repo` rerun surfaced one missing ownership claim for `tests/test_controller_automation_toolkit.py`; both issues were fixed on this workstream before the final `make remote-validate` and `make pre-push-gate` replays passed.
- The current realistic integrated version remains `0.178.3`; the next candidate version would be `0.178.4` once unrelated release blockers clear, and `Implemented In Repo Version` stays `not yet` until a later numbered release includes this exact-main closeout.
