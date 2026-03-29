# Workstream WS-0259: n8n Connector Fabric Live Apply

- ADR: [ADR 0259](../adr/0259-n8n-as-the-external-app-connector-fabric-for-serverclaw.md)
- Title: Re-verify the governed n8n lane as the external app connector fabric for ServerClaw
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/adr-0259-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/adr-0259-live-apply`
- Owner: codex
- Depends On: `adr-0151-n8n`, `adr-0206-ports-and-adapters`, `adr-0254-serverclaw`, `adr-0258-temporal`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0259-live-apply.md`, `docs/adr/0259-n8n-as-the-external-app-connector-fabric-for-serverclaw.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-n8n.md`, `config/service-capability-catalog.json`, `config/workflow-catalog.json`, `config/command-catalog.json`, `tests/test_validate_service_catalog.py`, `tests/test_n8n_metadata.py`, `receipts/live-applies/`

## Scope

- mark ADR 0259 as implemented by binding the already-live ADR 0151 n8n runtime
  to the ServerClaw product boundary instead of leaving it as an unclaimed
  standalone automation surface
- refresh the repo-managed service, workflow, command, and runbook metadata so
  operators can see that n8n is the third-party connector plane while
  assistant reasoning and long-lived orchestration stay outside n8n
- replay the governed n8n converge path from the latest `origin/main` state,
  verify the runtime end to end, and record fresh live-apply evidence

## Expected Repo Surfaces

- `docs/adr/0259-n8n-as-the-external-app-connector-fabric-for-serverclaw.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0259-live-apply.md`
- `docs/runbooks/configure-n8n.md`
- `config/service-capability-catalog.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `tests/test_validate_service_catalog.py`
- `tests/test_n8n_metadata.py`
- `workstreams.yaml`
- `receipts/live-applies/2026-03-29-adr-0259-n8n-serverclaw-connector-fabric-live-apply.json`

## Expected Live Surfaces

- `https://n8n.lv3.org/healthz` still returns `200` through the shared edge
- `https://n8n.lv3.org/` still redirects humans into the shared edge auth flow
- `https://n8n.lv3.org/webhook-test/...` remains reachable without the browser
  auth redirect so ServerClaw can use governed webhook adapters
- the guest-local readiness and owner-login checks still pass on
  `docker-runtime-lv3`

## Verification Plan

- run the focused ADR 0259 regression slice for the n8n metadata, playbook, and
  runtime-role contracts
- run repository automation and validation paths, including the full validation
  suite and the pre-push gate
- replay `make converge-n8n` from this isolated latest-`origin/main` worktree
- record direct probes for public health, public editor auth, public webhook
  reachability, guest-local readiness, and owner sign-in before updating ADR
  metadata

## Live Apply Outcome

Pending live replay.

## Live Evidence

Pending live replay.

## Mainline Integration Outcome

Pending merge to `main`.
