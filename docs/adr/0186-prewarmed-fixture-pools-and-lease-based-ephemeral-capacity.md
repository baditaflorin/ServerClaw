# ADR 0186: Prewarmed Fixture Pools and Lease-Based Ephemeral Capacity

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: pending merge to main
- Implemented In Platform Version: 0.130.31
- Implemented On: 2026-03-28
- Date: 2026-03-27

## Context

ADR 0088 made ephemeral fixtures possible, but cold-starting every environment from scratch is still slow enough that operators will be tempted to skip them during routine work. The platform also needs clearer ownership over who is consuming ephemeral capacity, for how long, and at whose expense.

Fast feedback matters most for:

- smoke-testing risky changes before merge
- restore rehearsals
- branch previews created on demand during review

## Decision

We will manage ephemeral compute as **lease-based capacity pools** with a small set of **prewarmed fixtures** per common template.

### Pool model

Each pool declares:

- template or image family
- domain and network attachment
- warm count and refill target
- maximum concurrent leases
- allowed placement classes

### Lease model

Every ephemeral allocation must record:

- owner identity
- purpose: `fixture`, `preview`, `recovery-drill`, or `load-test`
- created time
- expiry time
- protected capacity class consumed

### Warm fixtures

For high-frequency templates such as Debian base, Docker runtime, and Postgres test nodes, the platform should keep a small number of stopped or lightly initialized instances ready for rapid lease handoff. Refill happens asynchronously after a lease starts so the next requester does not pay the full creation penalty.

### Spillover rule

If local burst capacity is exhausted, preview and fixture leases should spill to the auxiliary cloud domain before touching standby or recovery reservations.

## Consequences

**Positive**

- Test and preview startup time drops enough to make ephemeral environments the normal path rather than the exceptional one.
- Ownership and TTL become visible, which makes cleanup and cost control far easier.
- Burst demand can be handled without silently borrowing HA headroom.

**Negative / Trade-offs**

- Warm pools consume resources even while idle.
- Pool refill and lease cleanup logic must be reliable or the speed advantage disappears.
- Different templates may require different warm strategies, which increases operational nuance.

## Boundaries

- This ADR governs ephemeral capacity allocation, not production standby failover.
- Prewarming is an optimization, not a substitute for deterministic provisioning from code.

## Related ADRs

- ADR 0088: Ephemeral infrastructure fixtures
- ADR 0106: Ephemeral VM lifecycle governance
- ADR 0157: Per-VM concurrency budget and resource reservation
- ADR 0183: Auxiliary cloud failure domain for witness, recovery, and burst capacity

## Implementation Notes

- The repository now carries a canonical warm-pool catalog, repo validation for that catalog, Windmill entrypoints for refill and expiry handling, and live-pool commands through `fixture_manager.py` and `lv3 fixture`.
- The first verified live proof used the `ops-base` pool end to end from the dedicated `codex/ws-0186-live-apply` worktree: prewarm, warm-handoff lease, in-guest verification over the Tailscale-backed Proxmox jump path, destroy, and refill back to `prewarmed`.
- The branch-local live-apply evidence is recorded in `receipts/live-applies/2026-03-28-adr-0186-prewarmed-fixture-pools-live-apply.json`.
- Merge to `main` still needs the protected integration surfaces updated there, not on this workstream branch: `README.md`, `VERSION`, `changelog.md`, and `versions/stack.yaml`.
