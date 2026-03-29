# Workstream WS-0261: Playwright Browser Runners Live Apply

- ADR: [ADR 0261](../adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md)
- Title: Live apply private Playwright browser runners for governed ServerClaw web action and extraction
- Status: in_progress
- Branch: `codex/ws-0261-playwright-browser-runners-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0261-playwright-browser-runners`
- Owner: codex
- Depends On: `adr-0069-agent-tool-registry`, `adr-0197-dify-canvas`, `adr-0247-authenticated-browser-journey-verification-via-playwright`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0261-live-apply.md`, `docs/adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-browser-runner.md`, `docs/runbooks/agent-tool-registry.md`, `playbooks/browser-runner.yml`, `playbooks/services/browser-runner.yml`, `collections/ansible_collections/lv3/platform/roles/browser_runner_runtime/**`, `scripts/browser_runner_service.py`, `scripts/browser_runner_client.py`, `scripts/browser_runner_smoke.py`, `requirements/browser-runner.txt`, `config/agent-tool-registry.json`, `scripts/agent_tool_registry.py`, `config/api-gateway-catalog.json`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/service-completeness.json`, `config/workflow-catalog.json`, `config/command-catalog.json`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `Makefile`, `tests/test_browser_runner_service.py`, `tests/test_browser_runner_client.py`, `tests/test_browser_runner_runtime_role.py`, `tests/test_generate_platform_vars.py`, `tests/test_agent_tool_registry.py`, `receipts/live-applies/`, `receipts/live-applies/evidence/`

## Scope

- add a private `browser_runner` service on `docker-runtime-lv3` for bounded Playwright session execution
- expose the runtime through the governed operator API gateway route `/v1/browser-runner/*`
- publish the governed Dify-compatible tool `browser-run-session`
- verify direct local runtime access, gateway access, and the Dify tool bridge end to end
- record branch-local live-apply evidence that can be replayed safely on exact latest `origin/main`

## Expected Repo Surfaces

- `playbooks/browser-runner.yml`
- `playbooks/services/browser-runner.yml`
- `collections/ansible_collections/lv3/platform/roles/browser_runner_runtime/**`
- `scripts/browser_runner_service.py`
- `scripts/browser_runner_client.py`
- `scripts/browser_runner_smoke.py`
- `requirements/browser-runner.txt`
- `config/agent-tool-registry.json`
- `scripts/agent_tool_registry.py`
- `config/api-gateway-catalog.json`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/service-completeness.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `docs/runbooks/configure-browser-runner.md`
- `docs/runbooks/agent-tool-registry.md`
- `docs/adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-runtime-lv3` exposes the private browser-runner API on port `8096`
- `api.lv3.org/v1/browser-runner/*` proxies the private browser-runner runtime for authenticated operators
- `api.lv3.org/v1/dify-tools/browser-run-session` dispatches bounded browser sessions through the governed tool registry
- bounded session artifacts persist under `/opt/browser-runner/data/artifacts`

## Verification Plan

- run the focused browser runner unit tests plus the related agent-tool and platform-vars regressions
- run `python3 scripts/validate_service_completeness.py --service browser_runner`
- run `./scripts/validate_repo.sh data-models agent-standards`
- run `make syntax-check-browser-runner` and `make syntax-check-api-gateway`
- live apply `make converge-browser-runner`
- verify direct private runtime access through a local tunnel with `scripts/browser_runner_smoke.py`
- verify the API gateway operator route and the Dify tool route using the same bounded smoke payload

## Merge-To-Main Notes

- protected integration files (`VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`, and release-note surfaces) intentionally remain untouched until the exact-main integration replay
