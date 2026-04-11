# ADR 0059: ntopng For Private Network Flow Visibility

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.53.0
- Implemented In Platform Version: 0.28.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The current monitoring plane shows host and guest resource usage, but it does not provide a clear visual view of:

- east-west traffic on the private network
- top talkers and protocol mix
- unusual connection patterns
- ingress versus guest-egress behavior during incidents

That gap makes network triage slower than it should be.

## Decision

We will add `ntopng` as the visual network-flow analysis surface for the private platform network.

Initial design:

1. `ntopng` runs directly on `proxmox-host`, where it can observe `vmbr10` and `vmbr0` without adding `nProbe` or a separate mirror fabric.
2. The first focus is the internal `10.10.10.0/24` guest network plus edge-adjacent ingress and guest-egress context.
3. Access is operator-only over the Proxmox host Tailscale path, not through the public edge.
4. Historical state remains host-local for triage and recent-history review, with no day-one long-term external flow export.

Primary use cases:

- identify unexpected talkers on `vmbr10`
- investigate guest-egress spikes
- compare normal versus incident traffic patterns
- support firewall, ingress, and backup traffic troubleshooting

## Consequences

- Operators gain a visual network triage tool instead of relying only on packet captures and counters.
- Agents can consume summarized flow information for anomaly detection or incident reports.
- Traffic collection stays close to the Proxmox bridge surfaces that actually carry guest traffic.
- The Proxmox host takes on a small additional observability workload and must keep packet-capture overhead under review.
- Flow retention and export remain explicitly bounded; no public publication or long-term external sink is introduced here.

## Boundaries

- ntopng is an observability aid, not an inline enforcement device.
- Packet capture by default is out of scope unless a follow-up ADR approves it.
- The tool must not expose private traffic metadata on public endpoints.
