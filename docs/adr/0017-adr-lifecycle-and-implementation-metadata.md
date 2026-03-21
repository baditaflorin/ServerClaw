# ADR 0017: ADR Lifecycle And Implementation Metadata

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.7.0
- Implemented In Platform Version: n/a
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

The existing ADR set only records whether a decision was accepted.

That is not enough for platform operations because accepted decisions and implemented decisions are not the same thing. Without explicit implementation metadata, it is harder to:

- identify which accepted decisions are still pending
- trace regressions to the version where a decision first became real
- distinguish documentation-only intent from live platform behavior

## Decision

Every ADR in this repository must carry these metadata fields near the top of the document:

- `Status`
- `Implementation Status`
- `Implemented In Repo Version`
- `Implemented In Platform Version`
- `Implemented On`
- `Date`

Allowed implementation states:

- `Implemented`
- `Partial`
- `Not Implemented`

Interpretation:

- repository version tracks when the decision first became true in repository code or contract
- platform version tracks when the decision first became true on the actual managed platform
- `n/a` is allowed when a field is intentionally repository-only
- `not yet` is required when implementation has not happened yet

## Consequences

- ADRs become useful for regression analysis, not just design history.
- Humans and agents can see immediately whether a decision is live, partial, or still pending.
- Repository-only governance ADRs no longer get confused with platform-state ADRs.
