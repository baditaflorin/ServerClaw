# ADR 0268: Fresh-Worktree Bootstrap Manifests For Generated Artifacts And Local Inputs

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.82
- Implemented In Platform Version: 0.130.56
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

Recent live-apply and repair receipts showed two recurring branch-local failure
classes:

- clean worktrees missing generated directories that a shared edge replay
  expected to publish
- controller-local token or file paths resolving differently across worktrees

These are not application defects. They are bootstrap defects that should be
caught before any converge or replay begins.

## Decision

We will require a **bootstrap manifest** for every fresh worktree path that can
run live-apply, repair, or main-merge automation.

### Manifest contents

- required generated directories and the command that materializes each
- required controller-local secret or token references
- required environment variables and helper paths
- optional read-only caches that may be reused

### Preflight rules

- every governed converge or live-apply entrypoint must run one bootstrap
  preflight first
- missing generated artifacts must be materialized before the main workflow
  continues
- missing local inputs must fail early with a precise bootstrap error instead
  of surfacing mid-converge

## Consequences

**Positive**

- fresh worktrees become predictable instead of implicitly depending on a dirty
  controller checkout
- shared edge and docs publication can rely on declared generated inputs
- secret-path and token-path errors fail early and readably

**Negative / Trade-offs**

- bootstrap manifests add another maintained artifact
- local operator environments must stay aligned with declared preflight inputs

## Boundaries

- This ADR governs worktree readiness for automation.
- It does not govern remote secret delivery inside the platform runtime.

## Related ADRs

- ADR 0038: Generated status documents from canonical state
- ADR 0081: Platform changelog and deployment history
- ADR 0132: Self-describing platform manifest
- ADR 0231: Local secret delivery for governed control-plane recovery
