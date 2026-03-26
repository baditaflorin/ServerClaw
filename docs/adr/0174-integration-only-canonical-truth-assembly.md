# ADR 0174: Integration-Only Canonical Truth Assembly

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-26

## Context

The repository intentionally protects `README.md`, `VERSION`, release sections in `changelog.md`, and canonical live-state summaries such as `versions/stack.yaml`. These files are valuable precisely because they represent integrated truth.

Parallel workstreams still need a way to express their local status, planned live changes, and observed outcomes without constantly colliding on those same files. Today that pressure creates either merge conflicts or pressure to put important state in chat instead of the repository.

## Decision

We will treat top-level canonical truth files as **integration-only assembled outputs**. Workstream branches will no longer edit these surfaces directly except during the explicit integration step.

### Source-of-truth split

Workstream branches write their state to branch-local sources:

- `docs/workstreams/*.md`
- workstream registry metadata in `workstreams.yaml`
- implementation receipts under `receipts/`
- ADR and runbook changes under `docs/`

Integration truth is assembled from those sources into:

- `README.md`
- `VERSION`
- `changelog.md`
- `versions/stack.yaml`

### Assembly model

An integration workflow will:

1. collect ready workstreams
2. verify their receipts, ADRs, and runbooks are present
3. assemble the canonical release-facing files
4. write those files only on the integration branch or `main`

### Branch rule

Feature and workstream branches must not claim success by editing canonical truth directly. They express readiness through workstream status and receipts; the assembler converts that into integrated truth later.

## Consequences

**Positive**

- Parallel workstreams stop fighting over shared release files.
- Canonical summaries become more trustworthy because they are derived from merged evidence.
- Integration becomes a concrete, reviewable step instead of an informal cleanup pass.

**Negative / Trade-offs**

- The assembler becomes an important piece of delivery infrastructure.
- Branch-local state may feel more indirect until the integration workflow is in place.

## Boundaries

- This ADR does not prevent emergency manual edits on `main`, but such edits are exceptions and must be documented.
- Branch-local docs remain first-class; only the top-level integrated summaries become assembly outputs.

## Related ADRs

- ADR 0036: Live-apply receipts
- ADR 0110: Platform versioning, release notes, and upgrade path
- ADR 0173: Workstream surface ownership manifest
- ADR 0182: Live apply merge train and rollback bundle
