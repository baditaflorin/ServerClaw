# Workstream WS-0240: Operator Visualization Panels Live Apply

- ADR: [ADR 0240](../adr/0240-operator-visualization-panels-via-apache-echarts.md)
- Title: Live apply Apache ECharts-backed operator visualization panels in the interactive ops portal
- Status: live_applied
- Implemented In Repo Version: pending main merge
- Live Applied In Platform Version: `0.130.42` context on the branch-local replay; canonical mainline bump still pending
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0240-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0240-live-apply`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal`, `adr-0104-service-dependency-graph`, `adr-0161-real-time-agent-coordination-map`, `adr-0205-capability-contracts-before-product-selection`
- Conflicts With: none
- Shared Surfaces: `scripts/ops_portal/**`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`, `docs/runbooks/ops-portal-down.md`, `docs/adr/0240-operator-visualization-panels-via-apache-echarts.md`, `docs/adr/.index.yaml`, `tests/test_interactive_ops_portal.py`, `receipts/live-applies/2026-03-28-adr-0240-operator-visualization-panels-live-apply.json`, `workstreams.yaml`

## Scope

- integrate Apache ECharts into the interactive ops portal as the default inline charting engine for first-party operator panels
- render repo-backed health, coordination, rollout, and topology visuals instead of introducing demo-only or one-off SVG widgets
- sync the canonical dependency graph into the portal runtime so the visual dependency focus can be rebuilt through normal repo automation
- live-apply the exact workstream branch state on `docker-runtime-lv3`, verify the published `ops.lv3.org` surface end to end, and leave a durable receipt

## Expected Repo Surfaces

- `scripts/ops_portal/app.py`
- `scripts/ops_portal/static/portal.css`
- `scripts/ops_portal/static/portal.js`
- `scripts/ops_portal/templates/base.html`
- `scripts/ops_portal/templates/index.html`
- `scripts/ops_portal/templates/partials/overview.html`
- `scripts/ops_portal/templates/partials/agents.html`
- `scripts/ops_portal/templates/partials/changelog.html`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`
- `tests/test_interactive_ops_portal.py`
- `docs/runbooks/ops-portal-down.md`
- `docs/adr/0240-operator-visualization-panels-via-apache-echarts.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0240-live-apply.md`
- `workstreams.yaml`

## Expected Live Surfaces

- the `ops-portal` runtime on `docker-runtime-lv3` serves the Apache ECharts client library and the new same-origin portal JavaScript bundle
- the portal overview renders a health-mix chart plus an `ops_portal` dependency-focus graph sourced from the repo-managed dependency graph
- the coordination section renders an ECharts session-state summary and the changelog section renders a live-apply cadence chart from mirrored receipts
- partial HTMX refreshes keep the charts live without duplicating browser-side listeners or requiring manual page refreshes

## Verification

- `python3 -m py_compile scripts/ops_portal/app.py`
- `uv run --with pytest --with pyyaml --with jsonschema --with-requirements requirements/ops-portal.txt python -m pytest -q tests/test_interactive_ops_portal.py`
- `uv run --with pytest --with pyyaml --with jsonschema --with-requirements requirements/ops-portal.txt python -m pytest -q tests/test_ops_portal.py`
- `make syntax-check-ops-portal`
- `make validate-data-models`
- `./scripts/validate_repo.sh agent-standards`
- `make converge-ops-portal`
- verify `http://10.10.10.20:8092/` and `https://ops.lv3.org/` render the new charts after the branch replay

## Live Apply Outcome

- the exact `codex/ws-0240-live-apply` runtime sources were replayed onto `docker-runtime-lv3` with `make converge-ops-portal`, and the portal role mirrored `config/dependency-graph.json` into `/opt/ops-portal/data/config/dependency-graph.json` alongside the existing receipt data set
- the running `ops-portal` container stayed healthy after the replay, the local health endpoint returned `{"status":"ok"}`, and the guest-local root page rendered the new `Health Mix`, `Topology Focus`, `Coordination Mix`, and `Live Apply Cadence` chart sections
- branch-local verification also confirmed the new same-origin JavaScript bundle at `/static/portal.js`, the inline ECharts option blocks on `/`, `/partials/overview`, `/partials/agents`, and `/partials/changelog`, and the public `https://ops.lv3.org` edge path still redirecting through the expected oauth2 sign-in flow with CSP allowing `https://unpkg.com`

## Mainline Integration Outcome

- pending main merge, release bump, and merged-main replay from `origin/main`

## Live Evidence

- branch-local live-apply receipt: `receipts/live-applies/2026-03-28-adr-0240-operator-visualization-panels-live-apply.json`
- branch-local guest health: `curl -fsS http://127.0.0.1:8092/health` returned `{"status":"ok"}` and `docker ps --filter name=ops-portal --format "{{.Image}} {{.Status}}"` reported `lv3-ops-portal:latest Up ... (healthy)`
- mirrored topology input: `/opt/ops-portal/data/config/dependency-graph.json`
- served chart runtime: `curl -fsS http://127.0.0.1:8092/static/portal.js | sed -n '1,12p'`
- served chart markup: `curl -fsS http://127.0.0.1:8092/partials/overview`, `curl -fsS http://127.0.0.1:8092/partials/agents`, and `curl -fsS http://127.0.0.1:8092/partials/changelog`
- public edge verification: `curl -k -I https://ops.lv3.org` returned `302` to `/oauth2/sign_in?rd=https://ops.lv3.org/`

## Merge-To-Main Notes

- still required on `main`: bump `VERSION`, update `changelog.md`, cut the next release note, update the top-level `README.md` integrated status summary, update `versions/stack.yaml` with the canonical platform version after a merged-main replay, and record a merged-main receipt if the final integration step replays `make converge-ops-portal` from `main`
