# Workstream WS-0253: Unified Runtime Assurance Scoreboard Live Apply

- ADR: [ADR 0253](../adr/0253-unified-runtime-assurance-scoreboard-and-rollup.md)
- Title: Operator-facing runtime assurance scoreboard and service-environment rollup
- Status: live_applied
- Implemented In Repo Version: 0.177.59
- Live Applied In Platform Version: 0.130.44
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0253-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0253-live-apply-r2`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal`, `adr-0113-world-state-materializer`, `adr-0209-use-case-services`, `adr-0244-runtime-assurance-matrix`
- Conflicts With: none
- Shared Surfaces: `scripts/ops_portal/`, `docs/adr/0244`, `docs/adr/0253`, `docs/runbooks/runtime-assurance-scoreboard.md`, `docs/adr/.index.yaml`, `workstreams.yaml`, `receipts/live-applies/`

## Scope

- compute one operator-facing runtime assurance rollup per active service and
  environment
- combine current health-composite data with publication metadata and
  receipt-backed evidence for route, smoke, auth, TLS, and logging dimensions
- render the new scoreboard inside the interactive ops portal and harden the
  live verification path so portal converges fail closed if the scoreboard is
  missing
- record live-apply evidence, ADR metadata, and the final release truth for
  the exact branch that became the verified merge-to-main candidate

## Non-Goals

- implementing every follow-on runtime assurance evidence source in this same
  workstream
- changing the platform baseline beyond `0.130.44` without a separate exact-main
  replay that proves a new first-live platform version
- redefining the gateway health-composite contract for unrelated consumers

## Expected Repo Surfaces

- `scripts/ops_portal/app.py`
- `scripts/ops_portal/runtime_assurance.py`
- `scripts/ops_portal/templates/partials/overview.html`
- `scripts/ops_portal/static/portal.css`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`
- `docs/runbooks/runtime-assurance-scoreboard.md`
- `docs/runbooks/ops-portal-down.md`
- `docs/adr/0244-runtime-assurance-matrix-per-service-and-environment.md`
- `docs/adr/0253-unified-runtime-assurance-scoreboard-and-rollup.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0253-live-apply.md`
- `receipts/live-applies/2026-03-29-adr-0253-unified-runtime-assurance-scoreboard-live-apply.json`
- `receipts/live-applies/2026-03-29-adr-0253-unified-runtime-assurance-scoreboard-latest-main-revalidation.json`
- `README.md`
- `VERSION`
- `RELEASE.md`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.59.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `workstreams.yaml`
- `tests/test_interactive_ops_portal.py`
- `tests/test_runtime_assurance_scoreboard.py`
- `receipts/live-applies/`

## Expected Live Surfaces

- `ops.lv3.org` renders a runtime assurance scoreboard that shows service and
  environment identity, per-dimension assurance state, evidence timestamps,
  owner, runbook, and next action
- the portal converge path verifies the scoreboard partial instead of proving
  only a generic shell render

## Verification

- `python3 -m py_compile scripts/ops_portal/app.py scripts/ops_portal/runtime_assurance.py`
  passed, and the focused pytest slice for
  `tests/test_interactive_ops_portal.py`,
  `tests/test_runtime_assurance_scoreboard.py`,
  `tests/test_ops_portal_runtime_role.py`, and
  `tests/test_ops_portal_playbook.py` passed with `31 passed in 1.52s`.
- `make syntax-check-ops-portal`, `make preflight WORKFLOW=converge-ops-portal`,
  `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`,
  `uv run --with pyyaml --with jsonschema python scripts/generate_ops_portal.py --check`,
  and `./scripts/validate_repo.sh agent-standards` all passed from the isolated
  worktree.
- The first full latest-`origin/main` replay exposed stale-controller
  interference rather than a current-branch regression: the launcher check
  failed with `404`, and `/opt/ops-portal/service/ops_portal/app.py` on
  `docker-runtime-lv3` matched stale hash `e86b15706d837ce6` from
  `.worktrees/ws-0244-live-apply` instead of the active latest-main worktree.
- After replaying again from commit `69fe90b21a2ccc76bee5d22aef4d79c32e656554`
  at repo version `0.177.72`, the full
  `make converge-ops-portal env=production` path completed successfully with
  `docker-runtime-lv3 : ok=125 changed=10 unreachable=0 failed=0 skipped=20 rescued=0 ignored=0`.
- Internal runtime checks on 2026-03-29 confirmed
  `http://10.10.10.20:8092/health` returned `200 {"status":"ok"}`,
  `http://10.10.10.20:8092/partials/overview` returned `200`,
  `http://10.10.10.20:8092/partials/launcher` returned `200`, and the
  converged `/opt/ops-portal/service/ops_portal/app.py` hash remained
  `a3330585cae1c40b` with `1906` lines, matching the latest-main worktree.
- Public edge checks on 2026-03-29 confirmed `https://ops.lv3.org/health`
  returned `HTTP 200` with `{"status":"ok"}`, and `https://ops.lv3.org/`
  returned `HTTP 302` to `/oauth2/sign_in`, preserving the authenticated shell
  behavior.

## Mainline Integration

- this branch became the final verified merge-to-main candidate for ADR 0253,
  so release `0.177.59` is the first repository version that records the
  runtime assurance scoreboard rollout
- the live platform baseline remains `0.130.44`; this workstream does not claim
  a new first-live platform version beyond that already-active baseline
- the first-live receipt remains
  `receipts/live-applies/2026-03-29-adr-0253-unified-runtime-assurance-scoreboard-live-apply.json`,
  and the latest-main revalidation receipt is
  `receipts/live-applies/2026-03-29-adr-0253-unified-runtime-assurance-scoreboard-latest-main-revalidation.json`
- this branch intentionally leaves `VERSION`, `changelog.md`, `README.md`, and
  `versions/stack.yaml` unchanged; only ADR-local and workstream-local
  verification evidence remains to merge safely onto `main`

## Notes For The Next Assistant

- the scoreboard is intentionally allowed to surface `unknown` dimensions; ADR
  0253 requires honest visibility for missing assurance rather than optimistic
  green rollups
- avoid moving the assurance builder outside `scripts/ops_portal/` unless the
  runtime role is also updated to sync the new shared module into production
- if launcher verification ever falls back to `404` again, compare the live
  host hash for `/opt/ops-portal/service/ops_portal/app.py` against stale hash
  `e86b15706d837ce6` from `.worktrees/ws-0244-live-apply` before treating the
  failure as a latest-main code regression
