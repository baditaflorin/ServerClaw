# Workstream WS-0236: TanStack Query Live Apply From Latest `origin/main`

- ADR: [ADR 0236](../adr/0236-server-state-and-mutation-feedback-via-tanstack-query.md)
- Title: live apply TanStack Query server-state conventions on the Windmill operator access admin app
- Status: live_applied
- Implemented Commit: `d21fb7c4ee93151cd3eb57f3dff09a3fa0d2022d`
- Implemented In Repo Version: `0.177.81`
- Live Applied In Platform Version: `0.130.43`
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0236-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0236-live-apply`
- Owner: codex
- Depends On: `adr-0122-windmill-operator-access-admin`, `adr-0209-use-case-services-and-thin-delivery-adapters`, `adr-0234-human-user-experience-architecture-bundle`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0236-server-state-and-mutation-feedback-via-tanstack-query.md`, `docs/adr/.index.yaml`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/runbooks/windmill-operator-access-admin.md`, `docs/runbooks/configure-windmill.md`, `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_compose_env.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/`, `tests/test_openbao_compose_env_helper.py`, `tests/test_windmill_operator_admin_app.py`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- adopt TanStack Query as the repo-managed server-state and mutation-feedback layer for the existing Windmill React admin surface
- replace page-local fetch lifecycle code with explicit query keys, invalidation, retry, stale-state, and background refresh behavior
- re-verify the raw app deployment path through the existing Windmill runtime converge and raw-app sync automation
- harden the shared Windmill automation path when latest-main converge uncovers raw-app dependency staging gaps or transient OpenBao policy-read races
- record branch-local live-apply evidence without updating protected integration files on this workstream branch

## Non-Goals

- introducing a second browser app outside the current Windmill admin surface
- rewriting server-rendered portal pages that do not use the React raw-app runtime
- updating `VERSION`, release notes, `README.md`, or `versions/stack.yaml` before the final mainline integration step

## Expected Repo Surfaces

- `docs/adr/0236-server-state-and-mutation-feedback-via-tanstack-query.md`
- `docs/workstreams/ws-0236-live-apply.md`
- `docs/adr/.index.yaml`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/runbooks/windmill-operator-access-admin.md`
- `docs/runbooks/configure-windmill.md`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_compose_env.yml`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package.json`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/index.tsx`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/App.tsx`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/index.css`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `tests/test_openbao_compose_env_helper.py`
- `tests/test_windmill_operator_admin_app.py`
- `receipts/live-applies/2026-03-28-adr-0236-tanstack-query-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- Windmill workspace `lv3` serves `f/lv3/operator_access_admin` with TanStack Query-backed roster and inventory queries
- operator onboarding, off-boarding, and roster reconciliation invalidate the affected query keys instead of forcing manual page reloads
- the live admin surface renders explicit loading, stale, error, and mutation feedback states for roster and inventory data

## Verification

- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_openbao_compose_env_helper.py tests/test_windmill_operator_admin_app.py` returned `10 passed in 5.69s`
- a temporary-copy raw app TypeScript replay with `npm install --include=dev --no-package-lock` and `npx tsc --noEmit` succeeded
- `make syntax-check-windmill` passed
- `./scripts/validate_repo.sh agent-standards` passed
- `make pre-push-gate` passed every branch-local check after the ownership and generated-diagram fixes; the only remaining failure was `schema-validation` reporting `build/platform-manifest.json` out of date, which is intentionally deferred to the protected mainline integration step
- `BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 make converge-windmill` passed with final recap `docker-runtime ok=226 changed=30 failed=0`, `postgres ok=63 changed=1 failed=0`, and `proxmox-host ok=36 changed=4 failed=0`
- authenticated Windmill API verification reported raw app path `f/lv3/operator_access_admin`, live app version `20`, and edit timestamp `2026-03-28T22:50:09.339380Z`
- authenticated Windmill app payload verification confirmed `@tanstack/react-query`, `QueryClientProvider`, `useQuery`, `useMutation`, and the expected `60s` plus `45s` refetch cadence markers in the deployed raw app files
- the private roster backend replay returned `{status: "ok", operator_count: 1, active_count: 1, inactive_count: 0}`
- the private app route `http://100.64.0.1:8005/apps/get/p/f/lv3/operator_access_admin` returned HTTP `200`

## Live Apply Outcome

- the latest-`origin/main` worktree replay completed successfully from commit `d21fb7c4ee93151cd3eb57f3dff09a3fa0d2022d`
- the Windmill raw-app sync now stages frontend dependencies before `wmill sync push`, which allowed the TanStack Query dependency to publish without manual host-side package installation
- the shared OpenBao compose-env helper retries current secret and policy reads, and the full latest-main converge completed without the earlier transient policy-read failure
- live Windmill now serves the operator admin raw app as version `20` with the TanStack Query cache provider and query plus mutation invalidation behavior embedded in the deployed payload

## Merge-To-Main Notes

- mainline integration completed in `ws-0236-main-merge`, which carries the
  exact-main replay into release `0.177.81`
- `receipts/live-applies/2026-03-29-adr-0236-tanstack-query-mainline-live-apply.json`
  records the later exact-main replay from repo version `0.177.80` on top of
  platform version `0.130.54` while this workstream retains the original
  branch-local live-apply evidence from `2026-03-28`
