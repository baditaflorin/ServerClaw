# Workstream WS-0236: Mainline Integration

- ADR: [ADR 0236](../adr/0236-server-state-and-mutation-feedback-via-tanstack-query.md)
- Title: Integrate ADR 0236 TanStack Query server-state feedback into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.81
- Platform Version Observed During Merge: 0.130.55
- Release Date: 2026-03-29
- Branch: `codex/ws-0236-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0236-mainline`
- Owner: codex
- Depends On: `ws-0236-live-apply`

## Purpose

Carry the verified ADR 0236 live apply onto the current `origin/main`, refresh
the protected canonical-truth and release surfaces, and preserve exact-main
verification for the TanStack Query-backed Windmill operator admin app without
overwriting the later ADR 0241 and ADR 0228 receipts that remain canonical for
the broader operator-access and Windmill surfaces.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0236-main-merge.md`
- `docs/workstreams/ws-0236-live-apply.md`
- `docs/adr/0236-server-state-and-mutation-feedback-via-tanstack-query.md`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.81.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/verify.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_postgres/tasks/main.yml`
- `config/windmill/scripts/gate-status.py`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package.json`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/index.tsx`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/App.tsx`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/index.css`
- `tests/test_validation_gate_windmill.py`
- `tests/test_windmill_default_operations_surface.py`
- `tests/test_windmill_operator_admin_app.py`
- `tests/test_world_state_repo_surfaces.py`
- `receipts/live-applies/2026-03-29-adr-0236-tanstack-query-mainline-live-apply.json`

## Verification

- `git fetch origin` kept this worktree current while other workstreams were
  active; the integration branch was rebased onto the latest `origin/main`
  release `0.177.80` before the exact-main replay.
- The focused Windmill and validation slice passed on the rebased integration
  worktree: `uv run --with pytest --with pyyaml python -m pytest -q
  tests/test_validation_gate_windmill.py tests/test_validation_gate.py
  tests/test_world_state_repo_surfaces.py
  tests/test_backup_coverage_ledger_windmill.py
  tests/test_windmill_default_operations_surface.py
  tests/test_windmill_operator_admin_app.py` returned `36 passed`.
- `make converge-windmill` completed successfully from the exact-main worktree
  with `docker-runtime-lv3 ok=248 changed=45 failed=0`, `postgres-lv3 ok=65
  changed=1 failed=0`, and `proxmox_florin ok=38 changed=7 failed=0`.
- Live Windmill verification after the replay reported app path
  `f/lv3/operator_access_admin`, app version `48`, edit timestamp
  `2026-03-29T15:11:20.200263Z`, route `http://100.64.0.1:8005/apps/get/p/f/lv3/operator_access_admin`
  returning `HTTP 200`, and deployed payload markers for
  `@tanstack/react-query`, `QueryClientProvider`, `useQuery`, `useMutation`,
  `invalidateQueries`, `60_000`, and `45_000`.
- The private operator roster replay returned `{status: "ok", operator_count:
  1, active_count: 1, inactive_count: 0}`, the seeded Windmill healthcheck
  returned `{probe: "ws-0236-post-converge", workspace: "lv3", job_id_present:
  true}`, and `f/lv3/gate-status` returned `status: ok` with the governed gate
  manifest plus waiver summary intact.
- The exact-main replay fixed real shared-worker drift: the worker checkout had
  a newer `scripts/gate_status.py` that imported a missing
  `gate_bypass_waivers` helper, so the Windmill wrapper now adds
  `/srv/proxmox_florin_server/scripts` to `sys.path` and falls back to an
  empty waiver summary only when that helper is absent. The replay also
  hardened transient Postgres readiness and default-script seeding races that
  surfaced only under concurrent live applies.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "platform version advances to 0.130.55 after the exact-main ADR 0236 replay re-verifies the TanStack Query-backed Windmill operator admin app while preserving the authenticated operator roster and validation-gate workflows on top of the 0.130.54 baseline" --released-on 2026-03-29`
  prepared release `0.177.81` with the single ws-0236 changelog note from the
  rebased integration worktree.

## Outcome

- Release `0.177.81` carries ADR 0236's exact-main replay onto `main`.
- The integrated platform baseline advances from `0.130.54` to `0.130.55`
  after the exact-main Windmill replay and verification complete.
- ADR 0236 still records `0.130.43` as the first platform version where the
  decision became true; this mainline receipt records the later exact-main
  revalidation carried into `main`.
- The broader `operator_access` and `windmill` latest-receipt pointers remain
  owned by the later ADR 0241 and ADR 0228 mainline receipts; ADR 0236's
  canonical evidence lives in
  `receipts/live-applies/2026-03-29-adr-0236-tanstack-query-mainline-live-apply.json`.
