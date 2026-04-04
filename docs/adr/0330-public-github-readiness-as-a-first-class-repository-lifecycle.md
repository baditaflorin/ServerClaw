# ADR 0330: Public GitHub Readiness As A First-Class Repository Lifecycle

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.5
- Implemented In Platform Version: N/A
- Implemented On: 2026-04-04
- Date: 2026-04-02
- Tags: github, publication, template, governance, public

## Context

This repository grew around one live deployment and one operator workflow. That
made the repo effective for rapid delivery, but it also allowed private context
to leak into public-facing surfaces:

- onboarding docs read like notes for one deployment instead of a forkable template
- generated docs emitted workstation-specific filesystem paths
- workstream metadata assumed one local checkout layout
- some root documents mixed public reference material with deployment-specific history

Preparing the repo for public GitHub publication is not a one-time cleanup. It
is an ongoing repository lifecycle with its own invariants.

## Decision

We will treat public GitHub readiness as a first-class repository lifecycle,
with explicit rules for public entrypoints, private overlays, and forkability.

### Public entrypoint rule

Root onboarding and summary surfaces must be safe to publish:

- `README.md`
- `AGENTS.md`
- `.repo-structure.yaml`
- `.config-locations.yaml`
- `workstreams.yaml`
- release indexes and generated root summaries

### Forkability rule

Committed metadata must default to repository-relative, example-friendly, and
portable contracts so a fresh fork can reuse the repo without first scrubbing
one operator's machine paths.

### Follow-through rule

Publicization work is complete only when generators, validators, and
documentation all reinforce the same constraints.

## Consequences

**Positive**

- publication becomes a governed capability instead of a manual cleanup sprint
- future merges have a clear definition of which surfaces must stay generic
- forks inherit a reproducible starting point rather than a private deployment diary

**Negative / Trade-offs**

- some existing deployment-specific history will need phased relocation or summarization
- validators will now reject patterns that previously slipped through
- public-safe summaries may intentionally show less live detail than private operator views

## Boundaries

- This ADR does not require every historical document to be rewritten in one pass.
- This ADR does not remove the ability to keep private overlays or local operator state.
- This ADR does not change the need for receipts and verified live truth on integrated mainline work.

## Related ADRs

- ADR 0038: Generated status documents from canonical state
- ADR 0163: Repository structure index for agent discovery
- ADR 0166: Canonical configuration locations registry
- ADR 0168: Automated enforcement of agent standards
