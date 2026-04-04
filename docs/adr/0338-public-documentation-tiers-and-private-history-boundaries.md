# ADR 0338: Public Documentation Tiers And Private History Boundaries

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: N/A
- Implemented On: 2026-04-04
- Date: 2026-04-02
- Tags: documentation, publication, history, boundaries, governance

## Context

The repository contains several kinds of documentation at once:

- public onboarding and architectural reference
- operational runbooks
- live receipts and deployment evidence
- historical workstream narratives

Not all of those need the same publication posture. Treating them all as either
fully public or fully private creates confusion and encourages drift in the root
surfaces.

## Decision

We will manage documentation with explicit public tiers and private-history
boundaries.

### Tier model

- public entrypoints: safe by default for GitHub readers
- public reference docs: reusable architectural or procedural material
- private overlays and live operations detail: deployment-specific history, artefacts, or identities kept out of public entrypoints

### Boundary rule

Root surfaces should summarize and link. They should not become the full home
for deployment-specific operational history when a deeper surface or private
overlay is more appropriate.

## Consequences

**Positive**

- publication decisions become clearer
- root surfaces stay concise and fork-friendly
- deeper docs can still exist without dominating public onboarding

**Negative / Trade-offs**

- some current historical narratives will eventually need relocation, summarization, or sensitivity review
- maintainers need discipline about which details belong in which tier

## Boundaries

- This ADR does not require deleting receipts or live evidence.
- This ADR does not create a new access-control system by itself.

## Related ADRs

- ADR 0134: Changelog redaction on the authenticated edge
- ADR 0328: Size-budgeted root summaries and automatic rollover ledgers
- ADR 0335: Public-safe agent onboarding entrypoints
