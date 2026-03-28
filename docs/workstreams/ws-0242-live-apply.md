# Workstream WS-0242: Guided Human Onboarding Live Apply

- ADR: [ADR 0242](../adr/0242-guided-human-onboarding-via-shepherd-tours.md)
- Title: Live apply task-oriented Shepherd tours into the browser-first operator
  access admin surface
- Status: in-progress
- Implemented In Repo Version: pending main integration
- Live Applied In Platform Version: pending verification
- Implemented On: pending verification
- Live Applied On: pending verification
- Branch: `codex/ws-0242-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0242-live-apply`
- Owner: codex
- Depends On: `adr-0108-operator-onboarding-and-offboarding`,
  `adr-0122-windmill-operator-access-admin`,
  `adr-0234-shared-human-app-shell-and-navigation-via-patternfly`
- Conflicts With: none
- Shared Surfaces: `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`,
  `docs/runbooks/windmill-operator-access-admin.md`,
  `docs/runbooks/operator-onboarding.md`,
  `docs/adr/0242-guided-human-onboarding-via-shepherd-tours.md`,
  `docs/adr/.index.yaml`, `tests/test_windmill_operator_admin_app.py`,
  `receipts/live-applies/`, `workstreams.yaml`

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
- `docs/runbooks/windmill-operator-access-admin.md`
- `docs/runbooks/operator-onboarding.md`
- `docs/adr/0242-guided-human-onboarding-via-shepherd-tours.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0242-live-apply.md`
- `tests/test_windmill_operator_admin_app.py`
- `receipts/live-applies/2026-03-28-adr-0242-guided-human-onboarding-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- Windmill raw app `f/lv3/operator_access_admin` exposes a first-run tour
  launcher and task-specific walkthroughs backed by Shepherd.js
- the onboarding tour is safe to skip, remembers dismiss and resume state in
  the browser, and points operators to the authoritative documentation path
- the repo-managed Windmill convergence path continues to seed and update the
  raw app without requiring ad hoc live edits

## Verification

- pending implementation

## Notes For The Next Assistant

- this workstream owns ADR 0242 live-apply evidence and the Windmill raw app
  tour implementation; keep protected integration files on `main` unless this
  branch becomes the final integration step
