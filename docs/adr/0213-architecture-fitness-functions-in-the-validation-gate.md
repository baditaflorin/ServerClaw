# ADR 0213: Architecture Fitness Functions In The Validation Gate

- Status: Accepted
- Implementation Status: Partial
- Implemented In Repo Version: 0.177.36
- Implemented In Platform Version: 0.130.36
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

Architecture guidance that exists only in ADR prose will drift. The repository
already uses validation gates for syntax, schemas, argument specs, and
idempotency, but it does not yet check many architectural promises that matter
for clean boundaries and vendor replaceability.

Without automated fitness functions:

- provider-specific imports can creep back into core layers
- duplicated policy constants can spread unnoticed
- missing exit plans or missing capability contracts stay invisible until a
  migration is already painful

## Decision

We will add architecture fitness functions to the repository validation gate.

The intended checks include:

- forbidden product-specific imports or payload types in core layers
- missing capability contracts for new critical provider selections
- missing replaceability scorecards or exit plans on critical product ADRs
- boundary bypasses where delivery code talks directly to a provider that should
  be behind a port
- duplicated shared policy constants that should come from a registry
- circular dependency violations across declared architecture layers

New fitness functions may begin as warn-only checks, but each one must declare a
path to eventual blocking enforcement if it proves useful.

## Implementation

The first implemented ADR 0213 fitness function is now live in
`scripts/replaceability_scorecards.py` and enforced through
`./scripts/validate_repo.sh architecture-fitness`.

This initial slice blocks merges when a governed critical product ADR is missing
its required ADR 0212 `Replaceability Scorecard` or `Vendor Exit Plan` fields.
The broader ADR 0213 scope remains partial because the other intended
architecture checks in this ADR are still follow-up work.

## Consequences

**Positive**

- the repository gains an automated way to self-correct architectural drift
- reviews can focus on intent and trade-offs instead of spotting every boundary
  violation manually
- future refactors can move faster because the gate watches for regressions

**Negative / Trade-offs**

- fitness functions require thoughtful tuning to avoid noisy false positives
- some current repo areas may fail the new standards and need staged adoption

## Boundaries

- This ADR defines the validation direction, not the exact first implementation
  wave.
- Fitness functions complement human review; they do not replace architectural
  judgment.
- Warn-only checks should not remain warn-only forever without an explicit
  reason.

## Related ADRs

- ADR 0031: Repository validation pipeline for automation changes
- ADR 0087: Repository validation gate
- ADR 0164: ADR metadata index
- ADR 0168: Ansible role idempotency CI enforcement
