# ADR 0191: Immutable Guest Replacement for Stateful and Edge Services

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-27

## Context

In-place upgrades are easy to start and hard to roll back. That trade-off becomes worse for services that matter to availability:

- ingress edge nodes
- databases with standbys
- monitoring and control-plane VMs

The repository already has template-based provisioning and rollback-bundle thinking, but risky service evolution still tends to drift toward mutation of long-lived machines rather than replacement of them.

## Decision

For stateful and edge services at redundancy tier `R1` or higher, the default change path will be **immutable guest replacement** rather than in-place mutation.

### Replacement model

The standard sequence is:

1. build or refresh the target image or template
2. provision a new guest with the intended configuration
3. join it as standby, preview target, or inactive edge peer
4. validate health and synthetic transactions
5. cut over traffic or leadership
6. retain the previous guest for a short rollback window

### When in-place change is allowed

In-place mutation is reserved for:

- emergency security fixes where replacement would be slower than the acceptable risk window
- low-tier services explicitly classified as rebuild-only
- narrow configuration changes already proven reversible

## Consequences

**Positive**

- Rollback becomes much faster and less ambiguous.
- Preview and standby validation naturally fit the same delivery path used for production cutover.
- Long-lived configuration drift is reduced.

**Negative / Trade-offs**

- Immutable replacement needs more temporary capacity during upgrades.
- Stateful services still need careful replication and cutover design; replacement does not remove that complexity.
- Some legacy services will need refactoring before they can follow this path cleanly.

## Boundaries

- This ADR changes the preferred delivery pattern; it does not require every guest to become cattle overnight.
- Immutable replacement does not remove the need for backups, rehearsals, or standby validation.

## Related ADRs

- ADR 0084: Packer template pipeline
- ADR 0085: OpenTofu VM lifecycle
- ADR 0179: Service redundancy tier matrix
- ADR 0182: Live apply merge train and rollback bundle
- ADR 0188: Failover rehearsal gate for redundancy tiers
