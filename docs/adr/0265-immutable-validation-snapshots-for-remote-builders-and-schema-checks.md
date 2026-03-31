# ADR 0265: Immutable Validation Snapshots For Remote Builders And Schema Checks

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.78
- Implemented In Platform Version: 0.130.53
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

Multiple gate-bypass receipts show the same fragile pattern: remote validation
operated against mirrored worktrees whose `.git` metadata, ownership manifests,
or path assumptions no longer behaved like a real repository. Validation then
failed for transport reasons instead of correctness reasons.

If remote checks cannot trust their own checkout shape, every higher-level
schema or dependency result becomes suspect.

## Decision

We will run remote builder and schema validation against **immutable repository
snapshots**, not mutable mirrored worktrees.

### Snapshot rules

- the controller must produce a content-addressed snapshot for each validation
  run
- the snapshot must contain the repository payload, commit identity, branch
  identity, and generation timestamp
- remote validators must unpack the snapshot into a fresh run namespace instead
  of reusing a mirrored mutable checkout

### Repository-shape rules

- schema validators must reason about repository content, not mirrored `.git`
  implementation details
- dependency-graph and generated-surface checks must consume the same immutable
  snapshot used by the rest of the run
- stale snapshot reuse is forbidden once the source commit changes

## Consequences

**Positive**

- remote validation failures become actionable content problems instead of git
  metadata accidents
- schema and generated-doc checks see one consistent repository image
- build handoff becomes auditable and reproducible

**Negative / Trade-offs**

- snapshot generation adds upload and storage overhead
- long-running builders need explicit cache strategy so immutable inputs do not
  imply wasteful full rebuilds

## Boundaries

- This ADR governs the artifact handed to validators, not lane blocking policy.
- It does not replace build caches; it constrains the source-of-truth input.

## Related ADRs

- ADR 0037: Schema-validated repository data models
- ADR 0082: Remote build execution gateway
- ADR 0117: Dependency graph runtime
- ADR 0229: Gitea Actions runners for on-platform validation and release
  preparation
