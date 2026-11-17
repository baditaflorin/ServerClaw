# Tailscale endpoint advertisement filter

This workstream evaluates an upstream, unmerged interface/address exclusion patch
for Linux Tailscale endpoint discovery. The stock daemon scans container bridges;
other peers may probe those unusable addresses. Retain the independent private WAN
egress guard: this patch removes configured candidates from an advertiser, not
unusable endpoints advertised by other peers.

`upstream-17762.patch` is a zero-context representation of the proposed upstream
change from <https://github.com/tailscale/tailscale/pull/17762>. Its checksum is
pinned. `build.sh` verifies the exact upstream source commit before applying it and builds a
static Linux/amd64 daemon on an approved builder using a pinned Go image. It
runs the upstream network-monitor tests plus `endpoint_filter_test.go`.

The canary installer is intentionally limited to the explicitly tested stock
releases 1.104.7 and 1.104.5. It refuses conflicting files, verifies the artifact hash, and arms a
five-minute local rollback before adding a systemd drop-in. An operator confirms
the canary only after independently checking peer endpoint advertisements,
Tailscale connectivity, the node's service paths, and the guard counters. A lost
session leaves the timer armed. `test-installer.sh` exercises the installer with
fake systemd in a disposable container and requires no host privileges.

The wrapper selects the patched daemon only when the vendor version and artifact
checksum match. If the package changes or the artifact fails verification, it
runs the vendor daemon instead. That preserves service availability but allows
unwanted discovery candidates to return; the existing WAN guard remains the
network safety boundary. The health timer emits a node-exporter textfile and the
Prometheus rules alert on an inactive or stale filter. The expected-runtime scrape job also alerts when a registered host has no filter metric, including a host that is unreachable or was never successfully scraped. Register each newly protected runtime in the managed monitoring inventory and verify the target; accidental removal of one target from that inventory still requires an independent inventory audit. A secondary alert remembers previously observed disappearing metrics for 24 hours. A new package version
requires a separately reviewed build, tests, and canary; this is not a promise of
automatic compatibility with future upstream updates.

Install only where the selected interface patterns are known to be container
bridges. The canary excludes `br-*`, `docker*`, and `veth*`, while leaving
physical and ordinary private LAN interfaces eligible. Review interface
ownership and version per node; do not exclude every private address or use a
single assumed interface mapping for the fleet.

The downstream sender filter also prevents discovery UDP packets to private,
carrier-grade NAT, or IPv4 link-local addresses unless the destination matches
an active directly connected subnet on an allowed interface. This retains
same-LAN discovery and avoids sending off-link private candidates to a public
default route. Public endpoints and DERP are not filtered. Private destinations
that are reachable only through a routed subnet may use public or relay paths;
verify any such deployment before enabling the filter. IPv6 is unchanged. The
interface snapshot is not a full policy-routing lookup, so the independent WAN
guard remains required.

For a host already running the previous reviewed binary, stage the new binary
and all scripts from the same reviewed commit, then use
`upgrade-canary.sh ARTIFACT SHA256 VERSION`. The script verifies the previous
build and its managed files, saves the previous binary, arms the existing local
rollback timer, and switches the daemon. Failure or a lost session restores the
previous verified filtered daemon; the WAN guard stays active. Confirm with `install-canary.sh commit`
only after checking off-link suppression, same-LAN discovery, Tailscale, the
node's service paths, and monitoring from an independent peer.

The sender-aware health script exports
`fleet_tailscale_endpoint_filter_sender_guard_active` only after verifying both
the patched daemon and its opt-in sender setting. The expected-host alert fires
if a registered node has no such metric or reports it inactive; during a staged
upgrade this correctly marks nodes still running the older advertisement-only
filter until they are upgraded.
