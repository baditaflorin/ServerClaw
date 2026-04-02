# Workstream ws-0311-live-apply: Live Apply ADR 0311 From Latest `origin/main`

- ADR: [ADR 0311](../adr/0311-global-command-palette-and-universal-open-dialog-via-cmdk.md)
- Title: Live apply a repo-managed `cmdk` command palette and universal open dialog on the Windmill operator access admin surface
- Status: merged
- Included In Repo Version: 0.177.142
- Branch-Local Receipt: `receipts/live-applies/2026-04-02-adr-0311-global-command-palette-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0311-global-command-palette-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.90
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Exact-Main Replay Baseline: repo `0.177.141`, platform `0.130.89`
- Branch: `codex/ws-0311-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0311-live-apply`
- Owner: codex
- Depends On: `adr-0108-operator-onboarding`, `adr-0121-local-search-and-indexing-fabric`, `adr-0122-windmill-operator-access-admin`, `adr-0239-browser-local-search-experience-via-pagefind`, `adr-0309-task-oriented-information-architecture-across-the-platform-workbench`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0311-live-apply.md`, `docs/adr/0311-global-command-palette-and-universal-open-dialog-via-cmdk.md`, `docs/adr/.index.yaml`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/runbooks/configure-windmill.md`, `docs/runbooks/windmill-operator-access-admin.md`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`, `config/windmill/scripts/command-palette-search.py`, `config/windmill/apps/wmill-lock.yaml`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`, `tests/test_command_palette_search.py`, `tests/test_windmill_operator_admin_app.py`, `receipts/ops-portal-snapshot.html`, `receipts/sbom/host-docker-runtime-lv3-2026-04-02.cdx.json`, `receipts/live-applies/2026-04-02-adr-0311-global-command-palette-live-apply.json`, `receipts/live-applies/2026-04-02-adr-0311-global-command-palette-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-ws-0311-*`

## Scope

- add a repo-managed backend search helper that reuses ADR 0121 search-fabric data for runbook and ADR results inside the live browser surface
- add a global `cmdk` command palette to the Windmill `operator_access_admin` raw app with favorites, recents, operator shortcuts, page jumps, glossary terms, and safe quick actions
- keep destructive or governed mutations behind the existing schema-first forms and guided-tour flows instead of bypassing confirmation or audit paths
- validate the raw app bundle, runtime seed metadata, and the broader repo automation paths from this isolated worktree before the live Windmill replay
- capture branch-local live-apply evidence and merge guidance without touching protected integration files on the workstream branch

## Non-Goals

- changing `VERSION`, `changelog.md`, `README.md`, or `versions/stack.yaml` before the final verified integration step on `main`
- replacing the existing ops-portal launcher or the docs-portal Pagefind surface on this workstream branch
- turning the command palette into a bypass around ADR 0108 governed access mutations

## Expected Repo Surfaces

- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/App.tsx`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/index.css`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/commandPalette.ts`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/backend/command_palette_search.yaml`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package.json`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package-lock.json`
- `config/windmill/apps/wmill-lock.yaml`
- `config/windmill/scripts/command-palette-search.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `docs/adr/0311-global-command-palette-and-universal-open-dialog-via-cmdk.md`
- `docs/workstreams/ws-0311-live-apply.md`
- `docs/adr/.index.yaml`
- `tests/test_command_palette_search.py`
- `tests/test_windmill_operator_admin_app.py`
- `workstreams.yaml`

## Expected Live Surfaces

- Windmill workspace `lv3` serves `f/lv3/operator_access_admin` with a global `Ctrl/Cmd+K` command palette that can open app sections, select operators, launch safe quick actions, and search canonical docs guidance
- the live palette returns ADR and runbook matches through the repo-managed `f/lv3/command_palette_search` helper rather than a hard-coded browser-only list
- favorites and recents stay browser-local while the search and governed actions continue to flow through repo-managed backend paths

## Ownership Notes

- `workstreams.yaml` and `docs/adr/.index.yaml` remain shared-contract surfaces and should be touched carefully so concurrent work can merge cleanly.
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`, `config/windmill/apps/wmill-lock.yaml`, `config/windmill/scripts/command-palette-search.py`, and the branch-local evidence files are exclusive to this workstream.
- protected integration surfaces stay deferred until the final `main` integration step even if the platform replay succeeds from this branch.

## Branch-Local Verification

- The earlier branch-local receipt remains preserved in `receipts/live-applies/2026-04-02-adr-0311-global-command-palette-live-apply.json` together with the first focused test, metadata, and targeted live-repair evidence.
- That branch-local evidence still matters because it captured the original shared-surface drift on `f/lv3/gate-status` before the later exact-main replay promoted the integrated truth safely.

## Exact-Main Verification

- `uv run --with pyyaml python3 scripts/release_manager.py status --json`, the patch dry run, and the actual release cut advanced the repo from `0.177.141` to `0.177.142`, while the later latest-main refresh on `origin/main` commit `67bc9f13f` still reported `Unreleased notes: 0`, confirming `0.177.142` remained the newest realistic repo cut for this replay.
- The exact-main tree passed the focused regression and bundle checks: `32 passed` across the ADR 0311, operator-admin, operator-manager, and journey-scorecard tests, raw-app `npm ci` plus `npx tsc --noEmit`, script `py_compile`, `make syntax-check-windmill`, and `make preflight WORKFLOW=converge-windmill`.
- The refreshed exact-main `make converge-windmill env=production` replay then completed successfully with recap `docker-runtime-lv3 : ok=329 changed=47 failed=0`, `postgres-lv3 : ok=93 changed=2 failed=0`, and `proxmox_florin : ok=41 changed=4 failed=0`.
- Post-replay live proof also succeeded: `f/lv3/command_palette_search` returned `{"status":"ok","query":"totp","count":5}`, the Windmill API still reports `CE v1.662.0`, and the live app summary now records `latest_version: 72` with the command-palette import, backend binding, CTA copy, `commandPalette.ts` file, and policy wiring all present.

## Exact-Main Validation

- After `origin/main` advanced again with ADR 0319 publication-only generated surfaces, the rebased tree refreshed the ADR index, canonical truth, status docs, platform manifest, dependency diagram, ops-portal snapshot, changelog portal, and Excalidraw diagrams again on top of that newer mainline.
- The final latest-main contract checks all passed: `./scripts/validate_repo.sh agent-standards`, `./scripts/validate_repo.sh workstream-surfaces`, `./scripts/validate_repo.sh data-models`, `python3 scripts/live_apply_receipts.py --validate`, `make validate`, `make remote-validate`, and `make pre-push-gate`.
- The canonical mainline receipt records the final repository automation and validation outcome for this promoted replay.

## Final Outcome

- ADR 0311 is now implemented in repository version `0.177.142` and live on platform version `0.130.90`.
- The private Windmill `f/lv3/operator_access_admin` surface now ships the `Ctrl/Cmd+K` and `/` palette flow, browser-local favorites plus recents, safe quick actions, operator and page jumps, glossary deep links, and docs-backed ADR plus runbook search without bypassing the governed ADR 0108 mutation flows.
- The promoted mainline replay preserved the already-live ADR 0316 journey analytics capabilities on the same operator-admin surface instead of overwriting them.
