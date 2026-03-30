# Workstream WS-0261: Playwright Browser Runners Live Apply

- ADR: [ADR 0261](../adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md)
- Title: Live apply private Playwright browser runners for governed ServerClaw web action and extraction
- Status: live_applied
- Implemented In Repo Version: pending merge-to-main version bump (latest replay baseline 0.177.92)
- Live Applied In Platform Version: 0.130.61
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0261-main-finish`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0261-main-finish`
- Owner: codex
- Depends On: `adr-0069-agent-tool-registry`, `adr-0197-dify-canvas`, `adr-0247-authenticated-browser-journey-verification-via-playwright`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0261-live-apply.md`, `docs/adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-browser-runner.md`, `docs/runbooks/agent-tool-registry.md`, `playbooks/browser-runner.yml`, `playbooks/services/browser-runner.yml`, `collections/ansible_collections/lv3/platform/roles/browser_runner_runtime/**`, `scripts/browser_runner_service.py`, `scripts/browser_runner_client.py`, `scripts/browser_runner_smoke.py`, `requirements/browser-runner.txt`, `config/agent-tool-registry.json`, `scripts/agent_tool_registry.py`, `config/api-gateway-catalog.json`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/service-completeness.json`, `config/workflow-catalog.json`, `config/command-catalog.json`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `Makefile`, `tests/test_browser_runner_service.py`, `tests/test_browser_runner_client.py`, `tests/test_browser_runner_runtime_role.py`, `tests/test_generate_platform_vars.py`, `tests/test_agent_tool_registry.py`, `receipts/live-applies/`, `receipts/live-applies/evidence/`

## Scope

The original ADR-local implementation branch was rebased forward into
`codex/ws-0261-main-finish` so the exact-main live replay can continue from the
latest realistic `origin/main` while preserving the ADR 0261 workstream state.
The successful replay baseline was `origin/main` commit
`bbb0f66b8ec995dfa3ecdd7bac9156ed664157cc` with `VERSION` `0.177.92` and
`platform_version` `0.130.61`.

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

## Live Apply Outcome

- `make converge-browser-runner env=production` completed successfully from the
  exact-main replay baseline and re-published the private browser-runner
  runtime plus the governed operator route
- the follow-up `make converge-api-gateway env=production` replays landed two
  branch-local fixes required by the packaged runtime: sibling `config/`
  resolution inside `/opt/api-gateway/service`, and automatic JSON
  `Content-Type` headers for governed Dify browser-runner calls
- the final browser-runner Dify replay completed with HTTP 200 and returned the
  expected heading, result text, screenshot artifact, and PDF artifact

## Live Evidence

- `receipts/live-applies/evidence/2026-03-30-adr-0261-0262-merged-origin-main-converge-browser-runner.txt`
- `receipts/live-applies/evidence/2026-03-30-adr-0261-merged-origin-main-browser-runner-private-verify.txt`
- `receipts/live-applies/evidence/2026-03-30-adr-0261-merged-origin-main-browser-runner-gateway-verify.txt`
- `receipts/live-applies/evidence/2026-03-30-adr-0261-merged-origin-main-converge-api-gateway-dify-header-fix.txt`
- `receipts/live-applies/evidence/2026-03-30-adr-0261-merged-origin-main-browser-runner-dify-verify.txt`
- branch-local canonical receipt:
  `receipts/live-applies/2026-03-30-adr-0261-playwright-browser-runners-live-apply.json`

## Remaining For Mainline Integration

- `origin/main` advanced during closeout to commit
  `46df65e7f2227ca79a38035d2d24f53b6c02b5f8` with `VERSION` `0.177.93` and
  `platform_version` `0.130.62`; the final merge path must reconcile this newer
  upstream before landing on `main`
- update the protected integration files only on the exact branch that lands on
  `main`: `VERSION`, `changelog.md`, `README.md`, and `versions/stack.yaml`
- replace the branch-local replay baseline metadata with the final merged repo
  version and canonical mainline live-apply receipt after the merge-to-main
  replay completes
