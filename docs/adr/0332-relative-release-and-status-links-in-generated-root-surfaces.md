# ADR 0332: Relative Release And Status Links In Generated Root Surfaces

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.143
- Implemented In Platform Version: N/A
- Implemented On: 2026-04-02
- Date: 2026-04-02
- Tags: release, readme, changelog, generation, links

## Context

The generated root surfaces were reintroducing private path leaks even when
humans cleaned them up manually. `README.md`, `changelog.md`, and
`docs/release-notes/README.md` were especially vulnerable because their
contents are regenerated and read first by new collaborators.

## Decision

Root summary generation must emit repository-relative links and avoid absolute
filesystem URLs.

### Governed surfaces

- generated sections inside `README.md`
- `changelog.md` release links
- `docs/release-notes/README.md`

### Output rule

- links inside repo-root documents must resolve from the repo root
- links inside `docs/release-notes/README.md` must resolve relative to that directory
- generated notices must point to committed scripts by repo-relative link

## Consequences

**Positive**

- generated root surfaces remain portable after every regeneration
- GitHub readers can follow links without translating local filesystem paths
- release tooling stops undoing public-readiness cleanup

**Negative / Trade-offs**

- the generators now intentionally prefer repo-native navigation over one local filesystem's absolute paths

## Boundaries

- This ADR governs link rendering, not which historical release notes exist.
- This ADR does not decide archive-size budgets; it only ensures the links that remain are portable.

## Related ADRs

- ADR 0038: Generated status documents from canonical state
- ADR 0081: Platform changelog and deployment history
- ADR 0331: Repository-relative paths for public metadata and generated docs
