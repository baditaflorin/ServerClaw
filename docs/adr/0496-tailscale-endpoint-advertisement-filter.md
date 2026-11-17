# ADR 0496: Filter container interfaces from Tailscale endpoint advertisements

- Status: Accepted
- Implementation Status: Partially implemented; seven advertisement-filter canaries verified; sender filter under test
- Implemented In Repo Version: 0.179.63
- Implemented In Platform Version: pending
- Implemented On: 2026-11-17
- Date: 2026-11-17

## Context

Tailscale's endpoint discovery can advertise IP addresses assigned to container
bridges. Peers that have no route to those private networks may still try them
as endpoint candidates. The fleet's independent private-WAN egress guards stop
packets from leaving a public interface, but those guards do not remove the
incorrect candidates or eliminate the originating discovery attempts. Filtering
all private addresses would also discard valid LAN paths.

The upstream proposal at <https://github.com/tailscale/tailscale/pull/17762>
adds interface and prefix exclusions but remains unmerged. Carrying a downstream
binary introduces security maintenance and compatibility risks.

## Decision

Evaluate the pinned upstream proposal on the exact installed upstream release.
Filter only confirmed container interfaces; leave normal LAN interfaces eligible. For IPv4 discovery sends, permit private, carrier-grade NAT, and link-local candidates only when they match an active directly connected subnet on an allowed interface; other private candidates fall back to public or relay paths. This is a conservative on-link check, not a complete policy-route lookup.
Use a bounded canary with an independent local rollback timer and verify the peer
network map, Tailscale connectivity, service flows, and the WAN guard before
confirming it. Keep the original packaged daemon and the WAN guard available.

A launcher must select the patched daemon only when its artifact checksum and
vendor package version match. On mismatch it uses the vendor daemon, so service
availability is preserved while the WAN guard remains the fallback protection.
Health metrics and alerts must identify a missing, stale, or inactive filter.
The custom build must be rebuilt and retested for each upstream release; do not
assume this temporary downstream patch stays compatible across upgrades.

## Implementation and verification

The patch and reproducible builder recipe are committed as the proposed
implementation. Unit tests and an isolated installer rollback harness are
required before live use. Live implementation begins only after a verified
canary and is recorded separately from repository merge and CI. Full fleet
coverage requires checking all advertising peers and their package versions;
offline or unmanaged nodes are not silently counted as covered.

## Consequences

- Container endpoints are not advertised on nodes where the verified filter runs. Once the sender filter is deployed, off-link private IPv4 discovery sends are suppressed on those nodes.
- Directly connected LAN and public endpoints remain available. Private endpoints reachable only through routed subnets may fall back to public or relay paths; every host's interface
  ownership must be checked before applying an exclusion pattern.
- An upstream upgrade can temporarily reintroduce candidates when the launcher
  deliberately falls back to the vendor binary; the WAN guard and alerts
  remain necessary until the downstream build is refreshed or upstream support
  becomes available.
- Rollback removes only the owned unit override and restarts the vendor daemon;
  it never deletes or replaces the Tailscale state file.
