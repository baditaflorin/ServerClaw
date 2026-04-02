# ADR 0331: Repository-Relative Paths For Public Metadata And Generated Docs

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.143
- Implemented In Platform Version: N/A
- Implemented On: 2026-04-02
- Date: 2026-04-02
- Tags: paths, portability, metadata, workstreams, docs

## Context

Public repository surfaces contained absolute workstation paths and checkout
assumptions such as user-home paths, repo-root paths, and temporary worktree
locations. Those references break portability and reveal private operator
context for no real benefit.

The highest-value fixes are the surfaces that are both committed and repeatedly
edited by automation:

- `workstreams.yaml`
- generated status docs
- release-note indexes
- root changelog links

## Decision

Committed public metadata and generated documentation must use repository-relative
paths instead of absolute workstation paths.

### Required scope

- workstream `doc` and `worktree_path` values are repository-relative
- generated root docs link to committed files by repo-relative path
- release metadata points at committed repo files instead of one machine's checkout

### Validation rule

Repository validation must reject new absolute path references in the governed
public entrypoints and workstream registry fields.

## Consequences

**Positive**

- the same metadata works in local clones, CI, and detached git worktrees
- the repo stops leaking one operator's machine layout
- workstream tooling can be reused in forks without per-user edits

**Negative / Trade-offs**

- old habits of copying absolute paths from one checkout now fail validation
- some historical documents may still need phased cleanup outside the governed root surfaces

## Boundaries

- This ADR governs committed metadata and generated doc links, not runtime paths such as `/etc/...`.
- This ADR does not ban ignored local state under `.local/`; it only bans committing personal absolute paths into public surfaces.

## Related ADRs

- ADR 0038: Generated status documents from canonical state
- ADR 0167: Agent handoff and context preservation
- ADR 0330: Public GitHub readiness as a first-class repository lifecycle
