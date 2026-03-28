# Workstream WS-0242: Guided Human Onboarding Live Apply

- ADR: [ADR 0242](../adr/0242-guided-human-onboarding-via-shepherd-tours.md)
- Title: Live apply task-oriented Shepherd tours into the browser-first operator
  access admin surface
- Status: in-progress (live applied, pending main integration)
- Implemented In Repo Version: pending main integration from latest origin/main
- Live Applied In Platform Version: 0.130.43
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0242-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0242-live-apply`
- Owner: codex
- Depends On: `adr-0108-operator-onboarding-and-offboarding`,
  `adr-0122-windmill-operator-access-admin`,
  `adr-0234-shared-human-app-shell-and-navigation-via-patternfly`
- Conflicts With: none
- Shared Surfaces: `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`,
  `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`,
  `docs/runbooks/configure-windmill.md`,
  `docs/runbooks/windmill-operator-access-admin.md`,
  `docs/runbooks/operator-onboarding.md`,
  `docs/runbooks/operator-offboarding.md`,
  `docs/adr/0242-guided-human-onboarding-via-shepherd-tours.md`,
  `docs/adr/.index.yaml`,
  `docs/diagrams/agent-coordination-map.excalidraw`,
  `scripts/validate_repo.sh`,
  `tests/test_windmill_operator_admin_app.py`,
  `receipts/live-applies/2026-03-28-adr-0242-guided-human-onboarding-live-apply.json`,
  `workstreams.yaml`

## Scope

- implement the first production Shepherd.js onboarding experience in a real
  first-party browser surface instead of leaving ADR 0242 as architecture-only
- keep the tour task-oriented, dismissible, resumable, and linked to the
  authoritative runbooks for the governed ADR 0108 operator workflows
- deploy the updated Windmill raw app from the latest `origin/main`, verify it
  on the live platform end to end, and record durable branch-local evidence
- leave protected release and canonical-truth files untouched on this branch
  unless this workstream becomes the final verified integration step on `main`

## Expected Repo Surfaces

- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/App.tsx`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/index.css`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package.json`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package-lock.json`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `docs/runbooks/operator-onboarding.md`
- `docs/runbooks/operator-offboarding.md`
- `docs/adr/0242-guided-human-onboarding-via-shepherd-tours.md`
- `docs/adr/.index.yaml`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/workstreams/ws-0242-live-apply.md`
- `scripts/validate_repo.sh`
- `tests/test_windmill_operator_admin_app.py`
- `receipts/live-applies/2026-03-28-adr-0242-guided-human-onboarding-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- Windmill raw app `f/lv3/operator_access_admin` exposes a first-run tour
  launcher and task-specific walkthroughs backed by Shepherd.js
- the onboarding tour is safe to skip, remembers dismiss and resume state in
  the browser, and points operators to the authoritative documentation path
- the repo-managed Windmill convergence path installs locked frontend
  dependencies for raw apps before `wmill sync push`
- the live app source matches this worktree after the corrective exact-worktree
  sync that removed stale `schemas.ts` and other older-shell residue

## Verification

- `make syntax-check-windmill` passed from rebased branch head `12b3e420935f8b1e10a0b1dc1da797ccdf80e793`.
- `./scripts/validate_repo.sh agent-standards` passed after the raw-app lockfile
  contract was added, and `uv run --with pytest --with pyyaml python -m pytest
  tests/test_windmill_operator_admin_app.py -q` returned `10 passed in 0.43s`.
- A Windmill-container dependency probe using the exact raw-app folder resolved
  `shepherd.js` successfully after `npm ci`, proving the same runtime image used
  by `make converge-windmill` can now build the app from the committed lockfile.
- `make converge-windmill` completed successfully from this worktree with final
  recap `docker-runtime-lv3 ok=232 changed=42 failed=0`,
  `postgres-lv3 ok=63 changed=1 failed=0`, and
  `proxmox_florin ok=37 changed=7 failed=0`.
- `curl -s http://100.64.0.1:8005/api/version` returned `CE v1.662.0`,
  `curl -s -H "Authorization: Bearer <secret>" http://100.64.0.1:8005/api/users/whoami`
  returned the managed bootstrap identity, and
  `curl -s -H "Authorization: Bearer <secret>" http://100.64.0.1:8005/api/w/lv3/apps/list`
  reported `f/lv3/operator_access_admin` as raw app version `15` edited at
  `2026-03-28T22:24:39.014189Z`.
- `apps/get/p/f/lv3/operator_access_admin` after the corrective sync returned
  only `/App.tsx`, `/index.css`, `/index.tsx`, `/package.json`, `/touring.ts`,
  and `/tsconfig.json`, with the tour launcher marker, Shepherd launcher copy,
  local-storage key `lv3.operator_access_admin.shepherd.v1`, and dependency
  `shepherd.js: 15.2.2` present in the live source.

## Live Apply Outcome

- ADR 0242 is live on the Windmill operator-admin surface, with the guided
  onboarding launcher, resumable Shepherd tours, and runbook-linked task flows
  available under `f/lv3/operator_access_admin`.
- The repo-managed Windmill automation now installs raw-app frontend
  dependencies with `npm ci` from committed lockfiles before `wmill sync push`,
  closing the live-apply failure that originally blocked the Shepherd rollout.
- Immediate post-converge verification exposed concurrent drift on the shared
  Windmill app staging surface: the live app still mixed an older schema-first
  `App.tsx` shell with the new `touring.ts` file. An exact-worktree
  `wmill sync push` from this branch corrected the live source, removed stale
  `/schemas.ts` and `backend/update_operator_notes.yaml`, and advanced the app
  to version `15`.

## Live Evidence

- live-apply receipt:
  `receipts/live-applies/2026-03-28-adr-0242-guided-human-onboarding-live-apply.json`
- live app path: `f/lv3/operator_access_admin`
- Windmill controller URL: `http://100.64.0.1:8005`
- app version after exact-worktree sync: `15`

## Merge-To-Main Notes

- remaining for merge to `main`: update `VERSION`, `changelog.md`, the top-level
  `README.md` integrated status summary, `versions/stack.yaml`, and the ADR 0242
  repo-version metadata from the pending placeholder to the final merged
  repository version.
- if another concurrent Windmill replay touches `f/lv3/operator_access_admin`
  before merge, rerun the exact-worktree `wmill sync push` and re-check
  `apps/get/p/f/lv3/operator_access_admin` before touching protected integration
  files.
