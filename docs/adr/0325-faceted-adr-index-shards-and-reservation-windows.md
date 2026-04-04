# ADR 0325: Faceted ADR Index Shards And Reservation Windows

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.4
- Implemented In Platform Version: N/A
- Implemented On: 2026-04-03
- Date: 2026-04-01
- Tags: adr, indexing, discovery, reservations, sharding

## Context

The repository now carries hundreds of ADRs and parallel workstreams continue to
author more. Two separate scaling problems now exist:

1. `docs/adr/.index.yaml` keeps growing into a large all-in-one discovery file.
2. Parallel ADR-writing threads can collide on the next available number unless
   they coordinate manually in chat.

The flat index was the right first step under ADR 0164, but it is now trying to
serve too many jobs at once: global discovery, concern queries, status filters,
latest-window navigation, and number allocation context.

## Decision

We will evolve ADR discovery into **faceted generated shards** and introduce a
**reservation ledger** for future ADR numbers.

### Sharded discovery outputs

ADR markdown files remain the canonical prose source. From that source, the repo
will generate:

- a compact root manifest at `docs/adr/.index.yaml`
- range shards such as `docs/adr/index/by-range/0300-0399.yaml`
- concern shards such as `docs/adr/index/by-concern/documentation.yaml`
- status shards such as `docs/adr/index/by-status/not-implemented.yaml`

The root manifest should answer quick onboarding questions and point callers to
the smaller shards, instead of embedding every record inline forever.

### Reservation ledger

Parallel ADR authoring will use a machine-readable reservation file, for example
`docs/adr/index/reservations.yaml`, that records:

- reserved single numbers or windows
- owning workstream or branch
- reason for the reservation
- reserved_on and optional expires_on timestamps

Scaffolding or validation tooling must refuse to allocate numbers that overlap an
active reservation.

### Number allocation rule

Future helper tooling should allocate the next free ADR number or requested
window by consulting both:

- the committed ADR corpus
- the active reservation ledger

This removes the need for hidden chat coordination when multiple agents prepare
new ADR batches.

## Consequences

**Positive**

- ADR discovery becomes faster because callers can read the facet they need
- the root index stays small enough to remain a practical onboarding file
- parallel ADR-writing workstreams can reserve windows explicitly in the repo
- the repository gains a reviewable audit trail for number allocation decisions

**Negative / Trade-offs**

- generators and validators must maintain another machine-readable surface
- a stale reservation ledger could block numbers until cleanup rules exist
- some legacy tooling may need compatibility support while it still expects one
  full `.index.yaml` file

## Boundaries

- This ADR does not require moving the ADR markdown files into new directories.
- This ADR is about discovery and numbering, not changing ADR writing style.
- Reservations are coordination metadata, not approval to merge low-quality ADRs.

## Related ADRs

- ADR 0164: ADR metadata index and fast discovery protocol
- ADR 0167: Agent handoff and context preservation
- ADR 0168: Automated enforcement of agent standards
- ADR 0174: Integration-only canonical truth assembly
