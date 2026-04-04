# ADR 0337: Fork-First Workstream And Worktree Metadata

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.4
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-04-04
- Date: 2026-04-02
- Tags: workstreams, worktrees, metadata, portability, forks

## Context

`workstreams.yaml` is central to how this repo coordinates parallel work, but it
had accumulated absolute checkout paths and machine-specific assumptions. That
undermines the very workflows the registry is supposed to support:

- detached git worktrees
- CI clones
- forks on a different filesystem layout
- continuation by other assistants

## Decision

Workstream and worktree metadata must be fork-first and repository-relative.

### Required fields

- `delivery_model.workstream_doc_root` is repository-relative
- `release_policy.breaking_change_criteria` is repository-relative
- each workstream `doc` path is repository-relative
- each workstream `worktree_path` is repository-relative

### Tooling rule

Validation and workstream tooling must treat absolute values in those metadata
fields as invalid.

## Consequences

**Positive**

- the registry works across forks and checkout layouts
- agents can continue a workstream without inheriting one person's local path
- repo metadata becomes more stable under branch and worktree churn

**Negative / Trade-offs**

- ad hoc local worktree naming is still possible, but committed metadata must normalize it to a portable form

## Boundaries

- This ADR governs registry metadata, not the operator's actual local filesystem.
- This ADR does not require every historical workstream narrative to be rewritten in one merge.

## Related ADRs

- ADR 0019: Parallel ADR delivery with workstreams
- ADR 0167: Agent handoff and context preservation
- ADR 0331: Repository-relative paths for public metadata and generated docs
