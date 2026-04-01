# ADR 0328: Size-Budgeted Root Summaries And Automatic Rollover Ledgers

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-04-01
- Tags: summaries, generation, rollover, readme, changelog

## Context

Several repo entrypoint documents are valuable precisely because they sit at the
top level and summarize integrated truth:

- `README.md`
- `changelog.md`
- `docs/release-notes/README.md`

The problem is not that they exist. The problem is that they only grow. As more
services, releases, and merged workstreams accumulate, those root surfaces risk
turning into append-only ledgers rather than concise operator entrypoints.

ADR 0038 already allows generated status sections, but it does not yet define
hard size budgets or rollover rules for root summaries.

## Decision

We will manage root summary surfaces with **explicit size budgets** and
**automatic rollover ledgers**.

### Root-summary rule

Each root summary document must declare a bounded purpose and keep only the
freshest entries needed for that purpose. For example:

- `README.md`: current platform overview plus the latest integrated highlights
- `changelog.md`: `Unreleased`, latest release, and a bounded recent-release list
- `docs/release-notes/README.md`: a bounded recent-release index plus archive links

### Rollover rule

When a summary exceeds its budget, generation tooling must move older entries to
deeper history surfaces rather than keep expanding the root document forever.
Likely targets include:

- yearly or range indexes under `docs/release-notes/index/`
- generated history pages under `docs/status/history/`
- existing portal-style history outputs already linked from the changelog

### Validation rule

Repo validation should fail if a generated root summary exceeds its declared
entry or line budget after regeneration.

## Consequences

**Positive**

- top-level docs remain readable entrypoints instead of archives
- the repo keeps rich history without forcing every reader through it
- generated summaries gain a concrete contract that can be tested
- agents can trust that the first read stays concise even as the platform grows

**Negative / Trade-offs**

- rollover generation must preserve stable links and predictable archive paths
- humans may need one extra click for older history
- the chosen budgets will need tuning as the repo evolves

## Boundaries

- This ADR does not delete historical release notes or changelog history.
- This ADR does not turn every top-level document into generated text.
- `Unreleased` remains first-class and should never be rolled away before a cut.

## Related ADRs

- ADR 0038: Generated status documents from canonical state
- ADR 0081: Deployment changelog generation
- ADR 0167: Agent handoff and context preservation
- ADR 0174: Integration-only canonical truth assembly
