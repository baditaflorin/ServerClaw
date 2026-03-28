# Workstream WS-0241: Rich Content And Inline Knowledge Editing Via Tiptap Live Apply

- ADR: [ADR 0241](../adr/0241-rich-content-and-inline-knowledge-editing-via-tiptap.md)
- Title: Live apply a repo-managed Tiptap editor for bounded operator knowledge inside the Windmill admin app
- Status: ready
- Implemented In Repo Version: not yet
- Live Applied In Platform Version: not yet
- Implemented On: not yet
- Live Applied On: not yet
- Branch: `codex/ws-0241-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0241-live-apply`
- Owner: codex
- Depends On: `adr-0108-operator-onboarding-and-offboarding`, `adr-0122-browser-first-operator-access-management`, `adr-0199-outline-living-knowledge-wiki`, `adr-0206-ports-and-adapters-for-external-integrations`
- Conflicts With: none
- Shared Surfaces: `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`, `config/windmill/scripts/operator-update-notes.py`, `scripts/operator_manager.py`, `roles/windmill_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`, `docs/runbooks/windmill-operator-access-admin.md`, `docs/adr/0241-rich-content-and-inline-knowledge-editing-via-tiptap.md`, `docs/adr/.index.yaml`, `tests/test_operator_manager.py`, `tests/test_windmill_operator_admin_app.py`, `receipts/live-applies/2026-03-28-adr-0241-rich-content-and-inline-knowledge-editing-live-apply.json`, `workstreams.yaml`

## Scope

- turn the existing Windmill Operator Access Admin into the first repo-managed bounded rich-content editing surface
- store operator notes as markdown in `config/operators.yaml` while editing them through Tiptap
- keep the browser app, Windmill wrapper, and `scripts/operator_manager.py` on one governed path rather than adding a second mutation surface
- replay the live Windmill converge from this isolated latest-`origin/main` worktree and verify the seeded raw app plus note-persistence path end to end
- leave protected integration files for the final merge-to-`main` step unless this branch becomes that step

## Expected Repo Surfaces

- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/App.tsx`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/index.css`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package.json`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/backend/update_operator_notes.yaml`
- `config/windmill/scripts/operator-update-notes.py`
- `scripts/operator_manager.py`
- `roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `docs/runbooks/windmill-operator-access-admin.md`
- `docs/adr/0241-rich-content-and-inline-knowledge-editing-via-tiptap.md`
- `docs/workstreams/ws-0241-live-apply.md`
- `tests/test_operator_manager.py`
- `tests/test_windmill_operator_admin_app.py`

## Expected Live Surfaces

- Windmill raw app `f/lv3/operator_access_admin` exposes a rich notes editor backed by Tiptap
- the live worker can persist bounded operator notes through the governed repo mutation path
- the repo-managed worker checkout stores the resulting markdown in `config/operators.yaml`

## Planned Verification

- focused operator-manager and Windmill raw-app regression tests
- Windmill syntax and data-model validation
- a latest-main `make converge-windmill` replay from this isolated worktree
- live verification that the raw app bundle and note-mutation wrapper are present on `docker-runtime-lv3`
- live verification that updating one operator note through the governed wrapper persists markdown into the worker checkout without regressing roster validation

## Merge-To-Main Notes

- protected integration files intentionally remain untouched on this workstream branch
