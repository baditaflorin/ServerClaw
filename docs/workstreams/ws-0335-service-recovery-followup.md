# Workstream ws-0335-service-recovery-followup: Recover The Remaining Degraded Services After Runtime-Pool Stabilization

- ADR: [ADR 0319](../adr/0319-runtime-pools-as-the-service-partition-boundary.md), [ADR 0320](../adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md)
- Title: Investigate and recover the remaining services that are still down or not responding properly after ws-0332 and ws-0333
- Status: in_progress
- Branch: `codex/ws-0335-service-recovery-followup`
- Worktree: `.worktrees/ws-0335-service-recovery-followup`
- Owner: codex
- Depends On: `ws-0332-homepage-triage`, `ws-0333-service-uptime-recovery`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `workstreams/active/ws-0335-service-recovery-followup.yaml`, `docs/workstreams/ws-0335-service-recovery-followup.md`, `receipts/live-applies/`

## Scope

- verify the live state of the runtime, control-plane, and Coolify-managed service surfaces from latest `origin/main`
- separate intentionally stopped services from crash-looping or misrouted services
- identify the remaining concrete blockers to uptime after the ws-0332 and ws-0333 protections landed
- apply the smallest safe repo-managed or documented live recovery needed to restore healthy service behavior
- record receipts and follow-up risks so later work does not have to rediscover the same failure classes

## Initial Questions

- which services are still down right now, on which guest, and are they `exited`, `restarting`, or only failing at the edge?
- are the remaining failures now app-local problems, missing-runtime prerequisites, stale publication state, or another shared-host issue?
- can the remaining unhealthy services be recovered from exact `main`, or do they require a new bounded fix first?

## Verification Plan

- inspect the current live container and publication state on the affected guests
- replay only the smallest safe repo-managed recovery path for the confirmed failures
- capture the evidence in `receipts/live-applies/`
