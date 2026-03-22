# ADR 0059: ntopng For Private Network Flow Visibility

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The current monitoring plane shows host and guest resource usage, but it does not provide a clear visual view of:

- east-west traffic on the private network
- top talkers and protocol mix
- unusual connection patterns
- ingress versus guest-egress behavior during incidents

That gap makes network triage slower than it should be.

## Decision

We will add ntopng as the visual network-flow analysis surface for the private platform network.

Initial design:

1. ntopng receives flow data or mirrored traffic from approved collection points.
2. The first focus is the internal `10.10.10.0/24` guest network and edge-related traffic patterns.
3. Access is operator-only and private-first.
4. Flow retention is sized for triage and recent-history review, not indefinite storage.

Primary use cases:

- identify unexpected talkers on `vmbr10`
- investigate guest-egress spikes
- compare normal versus incident traffic patterns
- support firewall, ingress, and backup traffic troubleshooting

## Consequences

- Operators gain a visual network triage tool instead of relying only on packet captures and counters.
- Agents can consume summarized flow information for anomaly detection or incident reports.
- Traffic-collection design must respect performance and privacy boundaries.
- Flow retention and export need explicit governance.

## Boundaries

- ntopng is an observability aid, not an inline enforcement device.
- Packet capture by default is out of scope unless a follow-up ADR approves it.
- The tool must not expose private traffic metadata on public endpoints.
