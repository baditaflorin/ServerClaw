# ADR 0019: Parallel ADR Delivery With Workstreams

- Status: Accepted
- Implementation Status: Accepted
- Implemented In Repo Version: N/A
- Implemented In Platform Version: n/a
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The repository has reached the point where multiple incomplete ADRs can be advanced independently. The previous operating model was effectively serial:

- one chat thread drove one change at a time
- changes often went directly to `main`
- `VERSION` was bumped too frequently for branch-local work
- there was no durable registry that mapped ADR implementation work to a branch, worktree, and scope boundary

That model is safe, but it makes parallel implementation slow and creates avoidable coordination overhead.

## Decision

We will separate architecture, implementation streams, and release:

1. ADRs remain the architecture truth.
   - ADRs define the decision and whether it is implemented at all.
   - ADRs do not need to model every branch-level implementation step.
2. Active implementation moves into workstreams.
   - every parallel implementation effort gets a workstream entry in `workstreams.yaml`
   - every active workstream gets a document in `docs/workstreams/`
   - one chat thread should normally own one workstream
3. Every workstream uses its own branch and preferably its own worktree.
   - branch names use the `codex/` prefix
   - workstream docs record dependencies, shared surfaces, verification, and merge criteria
4. Versioning happens at integration and release boundaries, not for every branch-local edit.
   - bump `VERSION` when work is merged to `main`
   - bump `platform_version` when merged work is applied live from `main`
   - update `versions/stack.yaml` only for `main` truth, not speculative branch intent
5. `changelog.md` uses an `Unreleased` section as the staging area before a mainline release cut.

## Consequences

- Multiple assistants can work in parallel without rewriting the same state files on every branch.
- `main` becomes the release/integration branch, not the scratchpad for every incomplete change.
- The workstream registry becomes the concurrency control layer for deciding which surfaces are safe to change in parallel.
- Operators must keep workstream docs current, or the parallel model will degrade back into hidden context and collisions.

## Sources

- /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/workstreams.yaml
- /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/workstreams/README.md
- /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/release-process.md
