# Workstream WS-0241: Rich Content And Inline Knowledge Editing Via Tiptap Live Apply

- ADR: [ADR 0241](../adr/0241-rich-content-and-inline-knowledge-editing-via-tiptap.md)
- Title: Live apply a repo-managed Tiptap editor for bounded operator knowledge inside the Windmill admin app
- Status: live_applied
- Implemented In Repo Version: not yet (pending main merge)
- Live Applied In Platform Version: 0.130.43
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0241-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0241-live-apply`
- Owner: codex
- Depends On: `adr-0108-operator-onboarding-and-offboarding`, `adr-0122-browser-first-operator-access-management`, `adr-0199-outline-living-knowledge-wiki`, `adr-0206-ports-and-adapters-for-external-integrations`
- Conflicts With: none
- Shared Surfaces: `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`, `config/windmill/apps/wmill-lock.yaml`, `config/windmill/scripts/operator-update-notes.py`, `scripts/operator_manager.py`, `roles/windmill_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`, `docs/runbooks/validate-repository-automation.md`, `docs/runbooks/validation-gate.md`, `docs/runbooks/windmill-operator-access-admin.md`, `docs/adr/0241-rich-content-and-inline-knowledge-editing-via-tiptap.md`, `docs/adr/.index.yaml`, `tests/test_operator_manager.py`, `tests/test_windmill_operator_admin_app.py`, `receipts/live-applies/2026-03-29-adr-0241-rich-content-and-inline-knowledge-editing-live-apply.json`, `workstreams.yaml`

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
- `config/windmill/apps/wmill-lock.yaml`
- `config/windmill/scripts/operator-update-notes.py`
- `scripts/operator_manager.py`
- `roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `docs/runbooks/validate-repository-automation.md`
- `docs/runbooks/validation-gate.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `docs/adr/0241-rich-content-and-inline-knowledge-editing-via-tiptap.md`
- `docs/workstreams/ws-0241-live-apply.md`
- `tests/test_operator_manager.py`
- `tests/test_windmill_operator_admin_app.py`

## Expected Live Surfaces

- Windmill raw app `f/lv3/operator_access_admin` exposes a rich notes editor backed by Tiptap
- the live worker can persist bounded operator notes through the governed repo mutation path
- the repo-managed worker checkout stores the resulting markdown in `config/operators.yaml`

## Verification

- focused operator-manager and Windmill raw-app regression tests
- regenerate the Windmill raw-app metadata lock after dependency changes
- Windmill syntax and data-model validation
- a latest-main `make converge-windmill` replay from this isolated worktree
- live verification that the raw app bundle and note-mutation wrapper are present on `docker-runtime-lv3`
- live verification that updating one operator note through the governed wrapper persists markdown into the worker checkout without regressing roster validation

## Live Apply Outcome

- `make converge-windmill` completed successfully from `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0241-live-apply` with final recap `docker-runtime-lv3 ok=231 changed=43 failed=0`, `postgres-lv3 ok=63 changed=1 failed=0`, and `proxmox_florin ok=36 changed=4 failed=0`
- live worker verification confirmed `/srv/proxmox_florin_server/scripts/operator_manager.py` hash `8c48a528d200389ec106dad7ef99d59d5fb1ff6891aa957c3503cf4f4359a77d`, `/srv/proxmox_florin_server/config/windmill/scripts/operator-update-notes.py` hash `7937e0fe94600789f75d777241ec50bb0b87cf81eca04e1454a84a09d870e5a8`, and the presence of `config/windmill/apps/wmill-lock.yaml` on `docker-runtime-lv3`
- live app proof in `receipts/live-applies/evidence/2026-03-29-adr-0241-app-summary.txt` confirmed `has_update_notes_backend: true`, `has_tiptap: true`, `has_editor_content: true`, `has_task_list: true`, and `has_insert_table: true` for `f/lv3/operator_access_admin`
- a governed `f/lv3/operator_update_notes` run updated operator `florin-badita` with the Tiptap-authored markdown and returned `changed: true`, `status: ok`, `note_length: 231`, and `roster_path: /srv/proxmox_florin_server/config/operators.yaml`
- a second governed `f/lv3/operator_update_notes` run restored the original operator note string and returned `changed: true`, `status: ok`, and `note_length: 65`, leaving the live roster content back at the original single-line note
- the final branch-local automation hardening covered both live-apply blockers discovered during replay: `config/windmill/apps/wmill-lock.yaml` is now a required validated raw-app surface, and the worker checkout archive now dereferences scoped-runner shard symlinks while using guest temp staging files so concurrent replays do not race on shared filenames

## Live Evidence

- live-apply receipt: `receipts/live-applies/2026-03-29-adr-0241-rich-content-and-inline-knowledge-editing-live-apply.json`
- Windmill converge replay: `receipts/live-applies/evidence/2026-03-29-adr-0241-converge-windmill-replay-3.txt`
- live app summary: `receipts/live-applies/evidence/2026-03-29-adr-0241-app-summary.txt`
- worker checkout hashes: `receipts/live-applies/evidence/2026-03-29-adr-0241-worker-checkout-hashes.txt`
- governed update result: `receipts/live-applies/evidence/2026-03-29-adr-0241-update-notes-result-success.txt`
- governed restore result: `receipts/live-applies/evidence/2026-03-29-adr-0241-restore-notes-result-success.txt`

## Merge-To-Main Notes

- protected integration files intentionally remain untouched on this workstream branch
- remaining for merge to `main`: update `VERSION`, `changelog.md`, the top-level `README.md` integrated status summary, and `versions/stack.yaml` during the protected mainline integration step
