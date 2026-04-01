# Workstream ws-0308-live-apply: Live Apply ADR 0308 From Latest `origin/main`

- ADR: [ADR 0308](../adr/0308-llm-agent-execution-surface-and-connectivity-contracts-for-operator-provisioning.md)
- Title: Live apply the operator provisioning execution-surface and connectivity contract from latest `origin/main`
- Status: in_progress
- Included In Repo Version: pending main integration
- Live Applied On: pending
- Platform Version Observed During Live Apply: 0.130.85
- Branch: `codex/ws-0308-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0308-live-apply`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0056-keycloak`, `adr-0108-operator-onboarding-and-offboarding`
- Conflicts With: `ws-0307-0308-operator-adrs`
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0308-live-apply.md`, `docs/adr/0308-llm-agent-execution-surface-and-connectivity-contracts-for-operator-provisioning.md`, `docs/runbooks/operator-onboarding.md`, `docs/adr/.index.yaml`, `config/workflow-catalog.json`, `scripts/preflight_controller_local.py`, `scripts/workflow_catalog.py`, `tests/test_preflight_controller_local.py`, `receipts/live-applies/`

## Scope

- make the operator-onboard preflight fail closed on real dependency outages instead of only checking controller-local secrets
- correct ADR 0308 and the operator onboarding runbook so they match the actual Windmill path, token file, guest SSH fallback, and controller-local tunnel requirements
- capture branch-local live verification evidence for the current Keycloak, OpenBao, and Windmill execution surface without touching protected release truth until the final mainline integration step

## Non-Goals

- changing `VERSION`, `changelog.md`, `README.md`, or `versions/stack.yaml` before the exact-main integration step
- inventing a second operator-provisioning implementation path outside the existing Windmill and `operator_manager.py` flow
- broad Keycloak or Windmill feature work unrelated to the ADR 0308 connectivity contract

## Expected Repo Surfaces

- `docs/adr/0308-llm-agent-execution-surface-and-connectivity-contracts-for-operator-provisioning.md`
- `docs/runbooks/operator-onboarding.md`
- `docs/workstreams/ws-0308-live-apply.md`
- `config/workflow-catalog.json`
- `scripts/preflight_controller_local.py`
- `scripts/workflow_catalog.py`
- `tests/test_preflight_controller_local.py`
- `docs/adr/.index.yaml`
- `workstreams.yaml`

## Expected Live Surfaces

- `https://sso.lv3.org/realms/lv3/.well-known/openid-configuration`
- `https://100.64.0.1:8200` as the private OpenBao mTLS edge
- `http://100.64.0.1:8005/api/version` as the private Windmill API proxy
- the SSH proxy path from the controller through `ops@100.64.0.1` to `ops@10.10.10.20`
- the Windmill worker path `f/lv3/operator_onboard`

## Ownership Notes

- `ws-0307-0308-operator-adrs` already touched ADR 0308, so this workstream explicitly records that conflict and must preserve only the latest exact-main truth.
- `docs/adr/.index.yaml` and `workstreams.yaml` remain shared-contract files and must be refreshed in a merge-safe way.
- Protected release truth is intentionally deferred until the exact-main integration step.

## Verification Plan

- focused repo tests for the workflow-catalog and controller preflight contract
- `make preflight WORKFLOW=operator-onboard` from this isolated worktree
- live controller checks for Keycloak discovery, OpenBao TLS handshake, Windmill API version, and the guest SSH proxy path
- a branch-local Windmill `operator_onboard` dry run plus a controller-local OpenBao tunnel verification path
- the repo automation gates needed for safe merge-to-main once branch-local work is complete
