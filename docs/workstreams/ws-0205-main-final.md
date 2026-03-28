# Workstream ws-0205-main-final

- ADR: [ADR 0205](../adr/0205-capability-contracts-before-product-selection.md)
- Title: Integrate ADR 0205 live apply into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.41
- Platform Version Observed During Merge: 0.130.39
- Release Date: 2026-03-28
- Branch: `codex/ws-0205-main-final`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0205-main-final`
- Owner: codex
- Depends On: `ws-0205-live-apply`
- Conflicts With: none

## Purpose

Carry the finished ADR 0205 capability-contract implementation onto the latest
`origin/main`, replay the `ops_portal` live apply from the merged candidate,
and refresh the protected integration truth only after the merged-main replay
is verified end to end.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0205-main-final.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/adr/0205-capability-contracts-before-product-selection.md`
- `docs/workstreams/adr-0205-capability-contracts-before-product-selection.md`
- `docs/adr/.index.yaml`
- `config/capability-contract-catalog.json`
- `scripts/capability_contracts.py`
- `scripts/platform_manifest.py`
- `scripts/ops_portal/app.py`
- `scripts/ops_portal/templates/partials/overview.html`
- `receipts/live-applies/2026-03-28-adr-0205-capability-contracts-before-product-selection*.json`
- `receipts/live-applies/evidence/2026-03-28-adr-0205-*.txt`

## Plan

- rebase the ADR 0205 implementation onto the latest `origin/main`
- validate the capability-contract catalog, platform manifest, and ops-portal regression slice
- replay `ops_portal` from the merged candidate and verify the live capability-contract panel
- update ADR metadata, release truth, receipts, and generated artifacts only after the live replay passes

## Result

- Release `0.177.41` carries the rebased ADR 0205 implementation onto `origin/main` after the concurrent ADR 0208 integration advanced the mainline first.
- The canonical platform state advanced to `0.130.39` after the merged-main `ops_portal` replay re-verified the contract-first catalog on the live operator surface.
- The merged-main receipt `receipts/live-applies/2026-03-28-adr-0205-capability-contracts-before-product-selection-mainline-live-apply.json` is now the source of truth for the final integration replay.

## Verification

- `LV3_SKIP_OUTLINE_SYNC=1 python3 scripts/release_manager.py --bump patch --platform-impact "bump platform version after the ADR 0205 merged-main ops-portal replay confirms the capability-contract catalog is live on top of the ADR 0208 mainline" --dry-run` confirmed current `0.177.40` and next `0.177.41`.
- `LV3_SKIP_OUTLINE_SYNC=1 python3 scripts/release_manager.py --bump patch --platform-impact "bump platform version after the ADR 0205 merged-main ops-portal replay confirms the capability-contract catalog is live on top of the ADR 0208 mainline"` prepared release `0.177.41`.
- `uv run --with pytest --with jsonschema --with-requirements requirements/ops-portal.txt python -m pytest tests/test_capability_contracts.py tests/test_platform_manifest.py tests/test_interactive_ops_portal.py -q` passed with `13 passed in 0.89s`.
- `uv run --with pyyaml python scripts/workstream_surface_ownership.py --validate-registry --validate-branch --base-ref origin/main`, `uv run --with pyyaml --with jsonschema python scripts/capability_contracts.py --validate`, and `./scripts/validate_repo.sh data-models generated-portals agent-standards` all passed on the integrated candidate.
- `make immutable-guest-replacement-plan service=ops_portal` selected the ADR 0191 `preview_guest` path with a `180m` rollback window before the live replay.
- `make live-apply-service service=ops_portal env=production ALLOW_IN_PLACE_MUTATION=true` completed with `docker-runtime-lv3 ok=99 changed=3 failed=0`, including local health and root-render checks in the play recap.
- `curl -fsS https://ops.lv3.org/health` returned `{"status":"ok"}`, and `curl -sSI https://ops.lv3.org/` returned `HTTP/2 302` to `https://ops.lv3.org/oauth2/sign_in?rd=https://ops.lv3.org/`, preserving the authenticated edge boundary while the capability-contract catalog remained live behind it.
