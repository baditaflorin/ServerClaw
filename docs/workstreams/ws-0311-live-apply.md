# Workstream ws-0311-live-apply: Live Apply ADR 0311 From Latest `origin/main`

- ADR: [ADR 0311](../adr/0311-global-command-palette-and-universal-open-dialog-via-cmdk.md)
- Title: Live apply a repo-managed `cmdk` command palette and universal open dialog on the Windmill operator access admin surface
- Status: live_applied
- Included In Repo Version: not yet
- Live Applied In Platform Version: 0.130.85
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Branch: `codex/ws-0311-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0311-live-apply`
- Owner: codex
- Depends On: `adr-0108-operator-onboarding`, `adr-0121-local-search-and-indexing-fabric`, `adr-0122-windmill-operator-access-admin`, `adr-0239-browser-local-search-experience-via-pagefind`, `adr-0309-task-oriented-information-architecture-across-the-platform-workbench`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0311-live-apply.md`, `docs/adr/0311-global-command-palette-and-universal-open-dialog-via-cmdk.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-windmill.md`, `docs/runbooks/windmill-operator-access-admin.md`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`, `config/windmill/scripts/command-palette-search.py`, `config/windmill/apps/wmill-lock.yaml`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`, `tests/test_command_palette_search.py`, `tests/test_windmill_operator_admin_app.py`, `receipts/live-applies/`, `receipts/live-applies/evidence/`

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

## Verification

- The branch-local metadata gate passed: `wmill generate-metadata` reported `All metadata up-to-date`, the targeted `cmdk` bundle compiled with `npm ci --no-audit --no-fund` plus `npx tsc --noEmit`, and `python3 -m py_compile config/windmill/scripts/command-palette-search.py` returned `py_compile ok`.
- The focused regression bundle passed with `28 passed in 0.58s` from `uv run --with pytest --with pyyaml python -m pytest tests/test_command_palette_search.py tests/test_windmill_operator_admin_app.py tests/test_operator_manager.py -q`.
- The repo validation slice passed from this worktree: `./scripts/validate_repo.sh agent-standards workstream-surfaces yaml json role-argument-specs data-models` and `./scripts/validate_repo.sh ansible-syntax`.
- The Windmill automation preflight path passed from this worktree: `make syntax-check-windmill` and `make preflight WORKFLOW=converge-windmill`.
- `make converge-windmill env=production` replayed the repo-managed worker checkout, seed scripts, and raw-app staging onto the live platform but failed closed in the shared verification task `f/lv3/gate-status`. The recorded Windmill job `019d4b2b-a00f-b7aa-fbd4-9b4dee1fe75f` returned `Internal: Result of job is invalid json (empty) @jobs.rs:835:20`, so the managed gate-status assertion stopped the converge before a false-green result could be recorded.
- A targeted repo-managed sync of `f/lv3/command_palette_search` then succeeded, and a live `scripts/windmill_run_wait_result.py` call returned `{"status":"ok","query":"totp","count":5}` with ADR and runbook matches from the live search-fabric index.
- A targeted repo-managed raw-app sync then repaired concurrent live drift on `f/lv3/operator_access_admin`; the Windmill API summary now records `latest_version: 58`, `has_command_palette_import: true`, `has_command_palette_backend: true`, `has_command_palette_cta: true`, `has_command_palette_file: true`, and `policy_has_command_palette_search: true`.

## Live Apply Outcome

- ADR 0311 is live on platform version `0.130.85` through the private Windmill app `f/lv3/operator_access_admin` and the repo-managed helper `f/lv3/command_palette_search`.
- The live browser surface now exposes the `Ctrl/Cmd+K` and `/` open flow, browser-local favorites plus recents, safe quick actions, operator and page jumps, glossary deep links, and docs-backed ADR and runbook search without bypassing the governed ADR 0108 mutation flows.
- The branch also records a concurrent shared-surface hazard: during this replay the live `f/lv3/gate-status` content diverged from the branch snapshot, so this workstream intentionally scoped the repair to the ADR 0311 app and helper surfaces instead of overwriting unrelated shared verification code out of band.

## Live Evidence

- `receipts/live-applies/evidence/2026-04-02-ws-0311-generate-metadata-r1.txt`
- `receipts/live-applies/evidence/2026-04-02-ws-0311-pytest-r1.txt`
- `receipts/live-applies/evidence/2026-04-02-ws-0311-validate-repo-r3.txt`
- `receipts/live-applies/evidence/2026-04-02-ws-0311-ansible-syntax-r1.txt`
- `receipts/live-applies/evidence/2026-04-02-ws-0311-syntax-check-windmill-r1.txt`
- `receipts/live-applies/evidence/2026-04-02-ws-0311-preflight-converge-windmill-r1.txt`
- `receipts/live-applies/evidence/2026-04-02-ws-0311-converge-windmill-r1.txt`
- `receipts/live-applies/evidence/2026-04-02-ws-0311-gate-status-failure-summary-r1.json`
- `receipts/live-applies/evidence/2026-04-02-ws-0311-command-palette-search-sync-r4.json`
- `receipts/live-applies/evidence/2026-04-02-ws-0311-command-palette-search-r4.json`
- `receipts/live-applies/evidence/2026-04-02-ws-0311-raw-app-sync-r1.txt`
- `receipts/live-applies/evidence/2026-04-02-ws-0311-live-app-summary-r2.json`

## Merge Criteria

- the raw app bundle, Windmill seed metadata, and focused command-palette tests pass from this isolated worktree
- the live palette plus backend search path are verified against the running platform even when unrelated shared verification surfaces require a separate exact-main closeout
- the branch records exactly which protected integration files still need the final `main` closeout after the live apply is done

## Merge-To-Main Notes

- This branch intentionally does not touch the protected mainline closeout surfaces: `VERSION`, release sections in `changelog.md`, the top-level `README.md` status summary, `versions/stack.yaml`, and any canonical generated truth surfaces still wait for the exact-main integration step.
- The exact-main integration branch should start from the latest `origin/main`, replay the repo-managed Windmill converge once the shared `f/lv3/gate-status` lane is stable, record the canonical mainline receipt, and only then update the protected release and integrated-truth files.
