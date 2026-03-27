# ADR 0192: Separate Capacity Classes for Standby, Recovery, and Preview Workloads

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.14
- Implemented In Platform Version: 0.130.31
- Implemented On: 2026-03-27
- Date: 2026-03-27

## Context

The platform now has several legitimate consumers of spare compute:

- production standby reservations
- restore and failover rehearsals
- branch previews and fixtures

If all spare capacity is treated as one shared pool, the most urgent or noisy workload wins. That is exactly how HA intent erodes in practice: preview demand borrows recovery space, recovery drills borrow standby headroom, and no one notices until an incident arrives.

## Decision

We will classify spare capacity into **separate reservation classes** with explicit admission rules.

### Capacity classes

The minimum classes are:

- `ha_reserved`: capacity protected for standby promotion and failover
- `recovery_reserved`: capacity protected for restore and disaster-recovery drills
- `preview_burst`: capacity available for previews, fixtures, and replay tests

### Admission rules

- `preview_burst` work may not consume `ha_reserved`.
- `recovery_reserved` may borrow from `preview_burst`, but only for declared drills.
- Borrowing from `ha_reserved` requires explicit break-glass evidence and must be time-bounded.
- When available, the auxiliary cloud domain should satisfy `preview_burst` demand first.

### Reporting

Current occupancy and blocked requests should be visible in machine-readable state and operator status views so that capacity starvation is a known fact, not a surprise.

## Consequences

**Positive**

- HA and DR guarantees are protected from casual test workload growth.
- Operators get clearer trade-offs when capacity is tight.
- Preview demand can scale without quietly weakening recovery posture.

**Negative / Trade-offs**

- Apparent spare capacity will look lower because protected pools are no longer treated as generally available.
- Admission control may frustrate users unless status reporting is clear and fast.

## Boundaries

- This ADR governs reservation policy, not the exact scheduler or allocator implementation.
- Capacity classes do not create resources by themselves; they only prevent self-inflicted contention.

## Implementation Notes

- The repository now models `ha_reserved`, `recovery_reserved`, and `preview_burst` directly in `config/capacity-model.json`.
- `scripts/capacity_report.py` renders the class totals and evaluates admission requests for preview, recovery-drill, and break-glass scenarios.
- `scripts/fixture_manager.py` now treats the reservation-backed `ephemeral_pool` as the canonical `preview_burst` surface, and `scripts/restore_verification.py` checks `recovery_reserved` before starting a drill.
- The live verification on 2026-03-27 used the branch commit `40df2935` against the real platform state.
- The implementation was merged into `main` and released in repository version `0.177.14` on 2026-03-28.

## Related ADRs

- ADR 0105: Platform capacity model and resource quota enforcement
- ADR 0157: Per-VM concurrency budget and resource reservation
- ADR 0179: Service redundancy tier matrix
- ADR 0180: Standby capacity reservation and placement rules
- ADR 0186: Prewarmed fixture pools and lease-based ephemeral capacity
