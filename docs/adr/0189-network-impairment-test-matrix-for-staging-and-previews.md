# ADR 0189: Network Impairment Test Matrix for Staging and Previews

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.22
- Implemented In Platform Version: 0.130.31
- Implemented On: 2026-03-27
- Date: 2026-03-27

## Context

Many of the platform's most likely failure modes are network-shaped rather than process-shaped:

- packet loss between app and database
- DNS resolution drift
- latency spikes during backup or replication
- asymmetric reachability between the dedicated host and auxiliary cloud

ADR 0171 introduced controlled fault injection, but the platform does not yet have a clear matrix for which network impairments should be tested, where they may be tested safely, and what behaviours must be asserted.

## Decision

We will define a **network impairment test matrix** for preview, fixture, standby, and recovery environments.

### Initial impairment set

The baseline matrix includes:

- added latency
- packet loss
- DNS resolution failure
- one-way dependency isolation
- temporary gateway loss
- TLS validation failure caused by trust or name mismatch

### Targeting rules

- Impairments should run first in previews and fixtures.
- Stateful standby and recovery targets may be used for higher-fidelity drills when the scenario requires replication or switchover behaviour.
- Primaries may only be impaired during explicit maintenance windows or break-glass validation.

### Assertion rule

Each service participating in the matrix must declare the expected behaviour:

- degrade gracefully
- queue and retry
- fail fast
- promote standby
- alert operator

## Consequences

**Positive**

- The platform gains repeatable evidence for network-shaped failure handling, not just process restarts.
- Preview environments become much more valuable for availability testing.
- Behavioural contracts stay visible as dependencies evolve.

**Negative / Trade-offs**

- High-fidelity network tests are more complex to set up and clean up than process-level drills.
- Some scenarios can still produce false confidence if the preview topology differs too much from live traffic patterns.

## Boundaries

- This ADR defines the matrix and safety rules; it does not replace the broader fault injection framework.
- The matrix is not a license to chaos-test primaries casually.

## Implementation Notes

- The first implementation ships a repo-managed matrix catalog, a report renderer, and a governed Windmill workflow that renders the selected target-class slice from the mirrored worker checkout.
- The 2026-03-27 live apply verified the safe `staging` diagnostic path only; actual preview, fixture, standby, and recovery impairments still depend on follow-up execution-lane work under ADR 0088 and ADR 0185.

## Related ADRs

- ADR 0072: Staging/production topology and environment separation
- ADR 0088: Ephemeral infrastructure fixtures
- ADR 0171: Controlled fault injection for resilience validation
- ADR 0185: Branch-scoped ephemeral preview environments
