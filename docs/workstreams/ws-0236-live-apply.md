# Workstream WS-0236: TanStack Query Live Apply From Latest `origin/main`

- ADR: [ADR 0236](../adr/0236-server-state-and-mutation-feedback-via-tanstack-query.md)
- Title: live apply TanStack Query server-state conventions on the Windmill operator access admin app
- Status: in_progress
- Branch: `codex/ws-0236-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0236-live-apply`
- Owner: codex
- Depends On: `adr-0122-windmill-operator-access-admin`, `adr-0209-use-case-services-and-thin-delivery-adapters`, `adr-0234-human-user-experience-architecture-bundle`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0236-server-state-and-mutation-feedback-via-tanstack-query.md`, `docs/adr/.index.yaml`, `docs/runbooks/windmill-operator-access-admin.md`, `docs/runbooks/configure-windmill.md`, `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_compose_env.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/`, `tests/test_openbao_compose_env_helper.py`, `tests/test_windmill_operator_admin_app.py`, `receipts/live-applies/`, `workstreams.yaml`

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

- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_windmill_operator_admin_app.py`
- run a TypeScript check for the raw app bundle in a temporary copy with `npm install` and `npx tsc --noEmit`
- `make syntax-check-windmill`
- `./scripts/validate_repo.sh agent-standards`
- `make converge-windmill`
- authenticated Windmill API and app-route verification for the updated `f/lv3/operator_access_admin` raw app

## Merge-To-Main Notes

- protected integration files must wait for the final `main` integration step after the live apply is verified
