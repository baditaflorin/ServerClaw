# Workstream WS-0261: Playwright Browser Runners Live Apply

- ADR: [ADR 0261](../adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md)
- Title: Live apply private Playwright browser runners for governed ServerClaw web action and extraction
- Status: live_applied
- Implemented In Repo Version: 0.177.95
- Live Applied In Platform Version: 0.130.61
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0261-main-finish`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0261-main-finish`
- Owner: codex
- Depends On: `adr-0069-agent-tool-registry`, `adr-0197-dify-canvas`, `adr-0247-authenticated-browser-journey-verification-via-playwright`
- Conflicts With: none
- Canonical Receipt: `receipts/live-applies/2026-03-30-adr-0261-playwright-browser-runners-live-apply.json`

## Purpose

Implement ADR 0261 by publishing the private `browser_runner` runtime on
`docker-runtime`, exposing the governed operator route at
`/v1/browser-runner/*`, and proving the governed Dify-compatible
`browser-run-session` tool end to end with receipt-backed artifacts.

## Replay Notes

- the first synchronized latest-main replay started from `origin/main` commit
  `bbb0f66b8ec995dfa3ecdd7bac9156ed664157cc` with `VERSION` `0.177.92` and
  `platform_version` `0.130.61`
- the final release cut and metadata integration landed in repository version
  `0.177.95`; the protected release surfaces and current platform baseline are
  tracked in [ws-0261-main-integration](./ws-0261-main-integration.md)
- the governed browser-runner path required one late shared-runtime hardening
  fix in the API gateway runtime so packaged deploys always ship `.gitea/`,
  `receipts/`, and clean away macOS AppleDouble sidecars before the container
  is rebuilt

## Verification

- `make converge-browser-runner env=production` completed successfully from the
  synchronized replay tree and re-published the private browser-runner runtime
- `make converge-api-gateway env=production` was re-run after the packaged
  runtime fix and again after the AppleDouble cleanup hardening; the final
  replays confirmed the live image and running container both contain
  `/app/.gitea/workflows/release-bundle.yml`,
  `/app/.github/workflows/validate.yml`, and `/app/receipts/...`
- `uv run --with pytest pytest -q tests/test_api_gateway_runtime_role.py`
  passed with `5 passed`
- the governed Dify smoke POST to
  `https://api.example.com/v1/dify-tools/browser-run-session` returned HTTP `200`
  with the expected heading `LV3 Browser Runner Smoke`, result
  `BROWSER RUNNER`, screenshot artifact, and PDF artifact
- the guest-side cleanup check returned `COUNT=0` for `find
  /opt/api-gateway/service -maxdepth 2 -name "._*"` after the final replay

## Evidence

- `receipts/live-applies/2026-03-30-adr-0261-playwright-browser-runners-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-adr-0261-0262-release-0.177.95-converge-api-gateway-retry-after-runtime-packaging-fix.txt`
- `receipts/live-applies/evidence/2026-03-30-adr-0261-0262-release-0.177.95-converge-api-gateway-sidecar-cleanup.txt`
- `receipts/live-applies/evidence/2026-03-30-adr-0261-0262-release-0.177.95-browser-runner-dify-smoke-postfix-headers.txt`
- `receipts/live-applies/evidence/2026-03-30-adr-0261-0262-release-0.177.95-browser-runner-dify-smoke-postfix-body.json`
- `receipts/live-applies/evidence/2026-03-30-adr-0261-0262-release-0.177.95-browser-runner-dify-smoke-postfix-payload.json`

## Outcome

- ADR 0261 is implemented in repository version `0.177.95`
- platform version `0.130.61` remains the first platform version where the
  browser-runner decision became true
- the integrated current platform baseline advances separately during the
  mainline integration closeout tracked in
  [ws-0261-main-integration](./ws-0261-main-integration.md)
