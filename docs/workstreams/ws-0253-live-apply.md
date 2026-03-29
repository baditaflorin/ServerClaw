# Workstream WS-0253: Unified Runtime Assurance Scoreboard Live Apply

- ADR: [ADR 0253](../adr/0253-unified-runtime-assurance-scoreboard-and-rollup.md)
- Title: Operator-facing runtime assurance scoreboard and service-environment rollup
- Status: live_applied
- Implemented In Repo Version: 0.177.59
- Live Applied In Platform Version: 0.130.44
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0253-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0253-live-apply`
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
  `tests/test_interactive_ops_portal.py` plus
  `tests/test_runtime_assurance_scoreboard.py` passed with `13 passed in 4.58s`.
- `make syntax-check-ops-portal`, `make preflight WORKFLOW=converge-ops-portal`,
  `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`,
  and `./scripts/validate_repo.sh agent-standards` all passed from the isolated
  worktree.
- The exact latest-`origin/main` targeted live apply succeeded with
  `docker-runtime-lv3 : ok=41 changed=11 unreachable=0 failed=0 skipped=8 rescued=0 ignored=0`
  after starting at `Reset the synced ops portal application tree before refresh`.
- Internal runtime checks on 2026-03-29 confirmed
  `http://10.10.10.20:8092/health` returned `200 {"status":"ok"}` and
  `http://10.10.10.20:8092/partials/overview` returned `200` from `uvicorn`
  with the converged overview partial.
- Public edge checks on 2026-03-29 confirmed `https://ops.lv3.org/health`
  returned `HTTP 200` with `{"status":"ok"}`, and `https://ops.lv3.org/`
  returned `HTTP 302` to `/oauth2/sign_in`, preserving the authenticated shell
  behavior.
- The outer `make converge-ops-portal` wrapper and the equivalent
  `ansible_scope_runner` path still received local exit `143` from the Codex
  execution environment before completion. The targeted playbook path, preflight
  gate, and live runtime verification all succeeded, so the branch records that
  wrapper limitation explicitly instead of treating it as platform failure.

## Mainline Integration

- this branch became the final verified merge-to-main candidate for ADR 0253,
  so release `0.177.59` is the first repository version that records the
  runtime assurance scoreboard rollout
- the live platform baseline remains `0.130.44`; this workstream does not claim
  a new first-live platform version beyond that already-active baseline
- the canonical live-apply receipt is
  `receipts/live-applies/2026-03-29-adr-0253-unified-runtime-assurance-scoreboard-live-apply.json`,
  and the `ops_portal` latest-receipt pointer should advance to that receipt
  when the release truth is assembled

## Notes For The Next Assistant

- the scoreboard is intentionally allowed to surface `unknown` dimensions; ADR
  0253 requires honest visibility for missing assurance rather than optimistic
  green rollups
- avoid moving the assurance builder outside `scripts/ops_portal/` unless the
  runtime role is also updated to sync the new shared module into production
- if the full outer `make converge-ops-portal` path is re-tested outside Codex,
  compare its result against this receipt before treating any local `143`
  termination as a platform regression
