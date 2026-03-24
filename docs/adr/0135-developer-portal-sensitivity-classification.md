# ADR 0135: Developer Portal Sensitivity Classification

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.112.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24
- Sensitivity: INTERNAL

## Context

The developer portal (ADR 0094) renders ADRs, runbooks, the service catalog, API reference, and operational reference tables into a single browsable site at `docs.lv3.org`.

That aggregation is useful, but documentation sensitivity is not uniform:

- some ADRs are safe to share broadly
- many runbooks and service references are appropriate only for authenticated operators
- recovery and compromise procedures should not be published in full in the normal portal view

The portal generator previously copied ADR and runbook markdown without any sensitivity metadata, redaction mode, or search-aware classification.

## Decision

We will classify developer-portal content by sensitivity and enforce that classification in the generated MkDocs source.

### Sensitivity levels

| Level | Portal behavior | Search behavior |
|---|---|---|
| `PUBLIC` | publish full text | full title and body remain searchable |
| `INTERNAL` | publish full text | full title and body remain searchable |
| `RESTRICTED` | publish title plus operator-safe summary only | only the generated summary page is searchable |
| `CONFIDENTIAL` | keep source-only; omit from portal indexes and copied pages | excluded from portal search because no published page is generated |

### Metadata contract

Source documents may declare sensitivity using either:

- YAML frontmatter field `sensitivity`
- the existing top metadata block field `Sensitivity`

Optional metadata fields:

- `portal_summary` or `Portal Summary`
- `justification` or `Justification`

Documents without a declared sensitivity default to `INTERNAL`.

### Generated portal contract

The docs generator now:

1. parses ADR and runbook sensitivity metadata
2. writes page-level frontmatter tags onto generated portal pages
3. shows a sensitivity notice at the top of each generated page
4. renders `RESTRICTED` ADRs and runbooks as summary-only portal pages
5. omits `CONFIDENTIAL` ADRs and runbooks from published portal indexes and copied output
6. stamps generated service, reference, release, and home pages with their default sensitivity (`INTERNAL` for internal operator material, `PUBLIC` for API reference)

This is intentionally a portal-rendering control, not a repository access control. The raw git repository remains the source of truth.

## Consequences

**Positive**

- Portal readers can immediately see the sensitivity of ADRs, runbooks, and generated reference pages.
- Sensitive recovery procedures no longer need to appear in full in the normal published portal path.
- Portal search now follows the same classification boundary as the rendered pages.

**Negative / Trade-offs**

- The static developer portal still does not provide a separate authenticated `platform-admin` full-text view; the raw repository remains the admin path for now.
- Existing ADRs and runbooks still need deliberate classification work over time; untagged documents fall back to `INTERNAL`.

## Boundaries

- This ADR governs the generated developer portal output only.
- It does not change raw repository visibility, git permissions, or live secret handling.
- It does not implement workflow-driven access request handling; that can be layered on later if the portal becomes role-aware.

## Related ADRs

- ADR 0031: Repository validation pipeline
- ADR 0075: Service capability catalog
- ADR 0094: Developer portal
- ADR 0110: Platform versioning and release path
- ADR 0121: Local search and indexing fabric
- ADR 0133: Portal authentication by default
