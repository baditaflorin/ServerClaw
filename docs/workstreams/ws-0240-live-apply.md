# Workstream WS-0240: Operator Visualization Panels Live Apply

- ADR: [ADR 0240](../adr/0240-operator-visualization-panels-via-apache-echarts.md)
- Title: Live apply Apache ECharts-backed operator visualization panels in the interactive ops portal
- Status: live_applied
- Implemented In Repo Version: 0.177.64
- Live Applied In Platform Version: `0.130.44`
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0240-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0240-live-apply`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal`, `adr-0104-service-dependency-graph`, `adr-0161-real-time-agent-coordination-map`, `adr-0205-capability-contracts-before-product-selection`
- Conflicts With: none
- Shared Surfaces: `scripts/ops_portal/**`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`, `docs/runbooks/ops-portal-down.md`, `docs/adr/0240-operator-visualization-panels-via-apache-echarts.md`, `docs/adr/.index.yaml`, `tests/test_interactive_ops_portal.py`, `receipts/live-applies/2026-03-28-adr-0240-operator-visualization-panels-live-apply.json`, `workstreams.yaml`

## Scope

- integrate Apache ECharts into the interactive ops portal as the default inline charting engine for first-party operator panels
- render repo-backed health, coordination, rollout, and topology visuals instead of introducing demo-only or one-off SVG widgets
- sync the canonical dependency graph into the portal runtime so the visual dependency focus can be rebuilt through normal repo automation
- live-apply the exact workstream branch state on `docker-runtime`, verify the published `ops.example.com` surface end to end, and leave a durable receipt

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

- the `ops-portal` runtime on `docker-runtime` serves the Apache ECharts client library and the new same-origin portal JavaScript bundle
- the portal overview renders a health-mix chart plus an `ops_portal` dependency-focus graph sourced from the repo-managed dependency graph
- the coordination section renders an ECharts session-state summary and the changelog section renders a live-apply cadence chart from mirrored receipts
- partial HTMX refreshes keep the charts live without duplicating browser-side listeners or requiring manual page refreshes

## Verification

- `python3 -m py_compile scripts/ops_portal/app.py`
- `uv run --with pytest --with pyyaml --with jsonschema --with-requirements requirements/ops-portal.txt python -m pytest -q tests/test_interactive_ops_portal.py tests/test_runtime_assurance_scoreboard.py tests/test_ops_portal.py`
- `make syntax-check-ops-portal`
- `make validate-data-models`
- `./scripts/validate_repo.sh agent-standards`
- `make converge-ops-portal`
- verify `http://10.10.10.20:8092/` and `https://ops.example.com/` render the new charts after the branch replay

## Live Apply Outcome

- the rebased `codex/ws-0240-live-apply` branch was exercised repeatedly through `make converge-ops-portal`; those runs surfaced and fixed the missing overlay-directory failure in `ops_portal_runtime`, but the scoped converge path from this workstation later hit a transient `DOCKER-FORWARD` chain recheck race and repeated local runner `SIGTERM` interruptions before the guest-local portal hashes actually changed
- because the guest-local service still served stale sources after the interrupted replays, the exact branch payload was mirrored manually into `/opt/ops-portal/service` and `/opt/ops-portal/data`, then rebuilt with `docker compose up -d --build --remove-orphans` on `docker-runtime`; this fallback used the same repo-managed runtime sources and left a documented manual receipt trail in this branch
- post-rebuild verification confirmed the running `ops-portal` container serves the branch-matching `app.py`, `runtime_assurance.py`, `overview.html`, `portal.css`, `portal.js`, and `requirements.txt` hashes; the local health endpoint returned `{"status":"ok"}`; the guest-local root page rendered the committed ECharts bundle; `/partials/overview` exposed both the runtime-assurance block and `data-echart-target` chart mounts; and `https://ops.example.com` still redirected through the expected oauth2 sign-in flow with CSP allowing `https://unpkg.com`

## Mainline Integration Outcome

- release `0.177.64` carries ADR 0240 onto `main`
- the exact-main replay from the integrated `0.177.63` candidate is recorded in
  `receipts/live-applies/2026-03-29-adr-0240-operator-visualization-panels-mainline-live-apply.json`
- the current platform baseline after the exact-main replay is `0.130.46`

## Live Evidence

- branch-local live-apply receipt: `receipts/live-applies/2026-03-28-adr-0240-operator-visualization-panels-live-apply.json`
- mainline replay receipt: `receipts/live-applies/2026-03-29-adr-0240-operator-visualization-panels-mainline-live-apply.json`
- branch-local guest health: `curl -fsS http://127.0.0.1:8092/health` returned `{"status":"ok"}` and `docker ps --filter name=ops-portal --format "{{.Names}} {{.Status}}"` reported `ops-portal Up ...`
- branch-local runtime hashes: `sha256sum scripts/ops_portal/app.py scripts/ops_portal/templates/partials/overview.html scripts/ops_portal/static/portal.css scripts/ops_portal/static/portal.js scripts/ops_portal/runtime_assurance.py requirements/ops-portal.txt` matched the same hash set under `/opt/ops-portal/service/...` on `docker-runtime`
- mirrored topology input: `/opt/ops-portal/data/config/dependency-graph.json`
- served chart runtime: `curl -fsS http://127.0.0.1:8092/static/portal.js | grep -E "echarts|data-echart-target"`
- served chart markup: `curl -fsS http://127.0.0.1:8092/partials/overview | grep -E "Runtime Assurance|data-echart-target"`
- public edge verification: `curl -k -I https://ops.example.com` returned `302` to `/oauth2/sign_in?rd=https://ops.example.com/`
- merged-main replay verification on 2026-03-29 confirmed `/opt/ops-portal/service/ops_portal/app.py`, `static/portal.js`, and `templates/partials/overview.html` matched the repository hashes after the container rebuild, `curl -fsS http://10.10.10.20:8092/health` returned `{"status":"ok"}`, and `curl -ks https://ops.example.com/health` returned `{"status":"ok"}`

## Automation Notes

- `make converge-ops-portal` and the equivalent direct mutation playbook launch
  were both re-tested from the integrated mainline candidate; in this Codex
  environment they still received local exit `143` / signal `15` before the
  remote apply could emit its first task output
- because that controller-local interruption persisted even after the release
  cut, the canonical merged-main replay used the documented staged
  service/data-sync fallback on `docker-runtime` before rebuilding the
  `ops-portal` container in place

## Merge-To-Main Notes

- completed in release `0.177.64`; no additional ADR 0240 merge-to-main work
  remains beyond future maintenance replays
