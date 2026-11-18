# Tailscale restart verification

Status: in progress. Base: `98ead578ce5590e75d2b0587d3d4f69f71d934d9`.

Verify the existing, monitored endpoint-discovery filter after a controlled guest reboot and continue the remaining rollout where safe. Preserve independent WAN guards and record live evidence without credentials.

On 2026-11-17 UTC, a quiet runtime was rebooted through its hypervisor. Its boot ID changed, the filtered Tailscale daemon and health timer started automatically, and an independent peer confirmed Tailscale connectivity and both sender-filter health metrics. The verifier initially used the wrong node-exporter directory; direct guest and independent exporter checks then verified the actual directory and healthy metric. This proves a guest reboot on that runtime, not a hypervisor reboot or a full host firewall reload.

On the same hypervisor, the owned nftables and physical-egress guard units were restarted sequentially, keeping the independent layer active throughout. Both units and their timer were enabled and active afterward; an unrouted private-address UDP send was rejected, and a public HTTPS request succeeded. The host firewall was not globally reloaded and the hypervisor was not rebooted.

The formerly delayed runtime was upgraded with the committed sender artifact and independent rollback timer. Peer endpoint filtering, service health, the node exporter, and both host guards passed before confirmation. A further OpenObserve runtime was installed using the same committed sender artifact and rollback timer; peer filtering, local service health, exporter metrics, and both host guards passed. The expected-host Prometheus job was extended to include it and all eight registered sender guards were scraped healthy. The pool hosting the two runtime VMs experienced substantial I/O pressure; its pool reported healthy, but the underlying cause remains unproven.

Remaining peers, including busy builders, still require inventory, safe rollout, and monitoring registration. Vendor version drift can select the stock daemon; the independent WAN guards remain the containment boundary.

A subnet router was then upgraded with the same rollback-protected sender artifact using an independent management path. An independent peer saw its LAN endpoint retained and Docker bridge removed; Tailscale connectivity, the sender metric, the local private VM route, the advertised subnet route, and both WAN guard layers passed before confirmation. It was added to the expected-host scrape inventory.

A builder was then upgraded with the verified artifact for its installed upstream release and a five-minute rollback timer. Its management path was independent of the guest daemon. An independent peer confirmed the Docker bridge endpoints disappeared, the LAN endpoint remained, Tailscale reconnected, and the sender metric was healthy; Docker and the exporter were active, and both host WAN guards passed before confirmation.

One remaining builder uses an older vendor release, so a separate context-anchored sender patch was prepared for its exact upstream source. Both focused upstream test suites passed in two independently cloned builds with separate build caches, and both static binaries had the same SHA-256. The build manifest selects and verifies the release-specific patch; Woodpecker also tests this release. This adds compatibility for the pinned release only; a future vendor version still requires a reviewed build.

The first older-release builder canary rolled back because its node exporter uses a different standard textfile directory. The exporter-directory allowlist now accepts that observed directory as well as the existing supported paths. The isolated installer harness verifies both layouts; the stock daemon and independent WAN guards stayed active after rollback.

The older-release builder was then installed with the reproducible, release-specific binary. The corrected health script recognised its node-exporter directory; an independent peer confirmed its LAN endpoint, absence of its Docker bridge endpoints, Tailscale connectivity and sender metric. Docker, the exporter, and both host WAN guards passed before confirmation.

Another builder was installed with the release-matched filter and rollback timer. Its existing Tailscale-only exporter already read the same default textfile directory, so no new listening port or exporter configuration was required. Independent peer, sender metric, Docker, exporter and both host guards passed before confirmation.

The build VM on the monitoring LAN was protected using the pinned release artifact. An independent peer observed bridge endpoints removed and LAN retained; the private exporter reported the sender guard, both CI agents remained running, and both host WAN guards passed before confirmation.

The inference builder was protected with the release-matched artifact and rollback timer. Its bridge endpoints disappeared while the LAN endpoint remained; an independent peer confirmed Tailscale and sender metrics, and Docker, its exporter, and both hypervisor WAN guards were active before confirmation.

The inference hypervisor was protected through an independent management path and timed rollback. Its LAN endpoint and subnet route remained present; an independent peer verified Tailscale and sender metrics, a private VM was reachable, and both WAN guards were healthy before confirmation.

A further public hypervisor was protected via independent management and a timed rollback. A peer confirmed its LAN endpoint and sender metric; both advertised private routes, local VM access and both WAN guards passed before confirmation.

The remaining active public hypervisor was protected using its independent management path and rollback timer. The first canary rolled back because the peer-name check used the wrong capitalization. A retry retained the LAN endpoint and both advertised private routes; an independent peer confirmed Tailscale and the sender metric, a private VM was reachable, and both WAN guards passed.

Four additional infrastructure guests, including a proxy, backup server, Git mirror and management service, received the same rollback-protected filter. An independent peer confirmed the preserved LAN endpoints and healthy sender metrics; the associated services and host WAN guards passed before confirmation.

The agent gateway VM received the sender filter with a rollback timer. A first attempt rolled back after a monitoring peer could not ping it over Tailscale; a second authorized peer succeeded. The gateway, dashboard and web service, private exporter, independent sender metric and host WAN guards passed before confirmation.

An online database primary still had dozens of established Tailscale client connections. Its daemon was not restarted, because doing so could interrupt live database clients; it remains behind the active monitored public-uplink guards. Two other peers were offline in the observed network maps, so their endpoint filtering could not be applied or verified. These remain open rollout items rather than evidence of full-fleet completion.
