# Workstream ws-0237-main-merge

- ADR: [ADR 0237](../adr/0237-schema-first-human-forms-via-react-hook-form-and-zod.md)
- Title: Integrate ADR 0237 schema-first human forms into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.74
- Platform Version Observed During Merge: 0.130.50
- Release Date: 2026-03-29
- Branch: `codex/ws-0237-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0237-main-merge`
- Owner: codex
- Depends On: `ws-0237-live-apply`

## Purpose

Carry the verified ADR 0237 schema-first operator-admin rollout onto the latest
`origin/main` after ADR 0234 advanced the mainline to `0.177.72`, cut the next
release from that synchronized baseline, refresh the protected canonical-truth
surfaces, and preserve the later ADR 0241 and ADR 0228 ownership of the shared
`operator_access` and `windmill` latest-receipt pointers.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0237-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.74.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/.index.yaml`
- `docs/adr/0237-schema-first-human-forms-via-react-hook-form-and-zod.md`
- `docs/workstreams/ws-0237-live-apply.md`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`
- `tests/test_windmill_operator_admin_app.py`
- `receipts/live-applies/2026-03-28-adr-0237-schema-first-human-forms-live-apply.json`
- `receipts/live-applies/evidence/2026-03-28-adr-0237-*`

## Verification

- refreshed the ws-0237 registry state on top of current `origin/main` after ADR 0234 advanced the synchronized release baseline to `0.177.72`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the verified ADR 0237 schema-first operator-admin rollout while the current mainline platform baseline remains 0.130.50 and the later ADR 0241 / ADR 0228 receipts stay canonical for shared operator_access and windmill evidence" --released-on 2026-03-29 --dry-run` reported `Current version: 0.177.73`, `Next version: 0.177.74`, and `Unreleased notes: 1`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the verified ADR 0237 schema-first operator-admin rollout while the current mainline platform baseline remains 0.130.50 and the later ADR 0241 / ADR 0228 receipts stay canonical for shared operator_access and windmill evidence" --released-on 2026-03-29` prepared release `0.177.74`
- `uv run --with pytest --with pyyaml python -m pytest tests/test_operator_manager.py tests/test_windmill_operator_admin_app.py -q` returned `25 passed`
- `python3 -m py_compile scripts/operator_manager.py config/windmill/scripts/operator-roster.py config/windmill/scripts/operator-inventory.py config/windmill/scripts/operator-update-notes.py` passed
- `tmpdir="$(mktemp -d)" && mkdir -p "$tmpdir/f/lv3" && rsync -a config/windmill/apps/f/lv3/operator_access_admin.raw_app/ "$tmpdir/f/lv3/operator_access_admin.raw_app/" && cd "$tmpdir/f/lv3/operator_access_admin.raw_app" && npm ci --no-audit --no-fund && npx tsc --noEmit` passed
- `make syntax-check-windmill` passed

## Outcome

- release `0.177.74` carries ADR 0237 onto `main`
- the integrated platform baseline remains `0.130.50`
- the canonical branch-local live evidence remains `receipts/live-applies/2026-03-28-adr-0237-schema-first-human-forms-live-apply.json`
- later ADR 0241 and ADR 0228 receipts remain the canonical latest live evidence for the broader shared `operator_access` and `windmill` surfaces
