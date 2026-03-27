# ADR 0182: Live Apply Merge Train and Rollback Bundle

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.175.3
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-27
- Date: 2026-03-26

## Context

The team wants many agents to prepare work in parallel without turning live application into chaos. Preparation can be highly parallel:

- ADRs can be drafted concurrently
- roles and playbooks can be built in separate worktrees
- dry-runs and contract tests can fan out

Live application is different. At that point the platform has one real state, one operator blast radius, and a small set of shared control surfaces. Without a disciplined integration step, the system risks partial applies, unclear rollback boundaries, and canonical truth drifting from what was actually promoted.

## Decision

We will use a **live apply merge train** that batches ready workstreams into a reviewed integration set and requires a rollback bundle before mutation begins.

### Merge train inputs

A workstream may enter the train only when it has:

- declared surface ownership
- required ADR and runbook updates
- passing contract and validation checks
- an apply plan or dependency wave manifest
- a rollback bundle definition

### Rollback bundle

Each train item must declare the fastest credible reversal path, such as:

- `git revert` only
- restore previous rendered config and rerun play
- promote standby or restore snapshot
- operator break-glass runbook

### Apply rule

- train items affecting disjoint shards may apply in the same wave
- train items touching the same shared surface group must serialize
- canonical truth files are updated only after apply outcome is confirmed

## Consequences

**Positive**

- Parallel preparation remains fast while live mutation stays controlled.
- Every change arrives with a rollback story before the risky step starts.
- Integration truth stays aligned with what was actually applied.

**Negative / Trade-offs**

- The merge train adds ceremony before live apply.
- Some ready workstreams will wait behind a shared-surface bottleneck.

## Implementation Notes

The repository implementation now ships:

- `platform/live_apply/merge_train.py` for queue state, wave planning, rollback bundle generation, and rollback execution
- `scripts/live_apply_merge_train.py` plus `make live-apply-train-*` targets for operators
- `scripts/validate_repository_data_models.py` validation for train-eligible `workstreams.yaml` metadata
- `docs/runbooks/live-apply-merge-train.md` for the operator workflow

This ADR currently claims repository implementation only. No live platform version is recorded until the train is exercised from `main` against the real environment.

## Boundaries

- This ADR governs promotion and live mutation, not day-to-day branch development.
- A rollback bundle is not a guarantee of zero downtime; it is a requirement for explicit recovery intent.

## Related ADRs

- ADR 0036: Live-apply receipts
- ADR 0073: Environment promotion gate and deployment pipeline
- ADR 0174: Integration-only canonical truth assembly
- ADR 0178: Dependency wave manifests for parallel apply
