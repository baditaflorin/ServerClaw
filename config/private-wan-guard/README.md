# Private IPv4 public-uplink guards

The host nftables policy drops private, CGNAT and IPv4 link-local destinations in the output and forward hooks only when the public logical WAN interface is selected. A second, independent `tc flower` egress filter on the physical uplink blocks the same IPv4 ranges even if nftables is flushed. Neither filter applies to packets routed over a private interface. IPv6, VLAN-encapsulated frames, and non-IP protocols are not covered by this IPv4 policy.

The installer is intended for a reviewed, verified host, not bulk discovery. On each host, establish the logical WAN device from `ip route get` and its actual physical port from the bridge membership; inspect existing qdiscs and egress filters first. The installer reserves preference 49000, handles 1–5, refuses conflicting filters and never removes an existing qdisc. It installs a boot-time nft service, a device-bound TC service and a one-minute reconciliation timer. The timer repairs missing layers, logs the event and exports `fleet_private_wan_guard_*` metrics to node_exporter. A full ruleset flush can temporarily remove the nft layer, but the physical TC layer does not depend on nftables. Privileged deletion of both guards, replacement of the NIC or competing network configuration can still defeat the controls; alerting and independent verification are required.

Deploy from the reviewed merged tree, one hypervisor at a time, under the platform's apply lock:

```sh
sudo ./config/private-wan-guard/install-host.sh PHYSICAL_INTERFACE NFT_INTERFACE
sudo systemctl restart private-wan-guard-tc@PHYSICAL_INTERFACE.service
sudo /usr/local/sbin/wan-guard-tc.sh verify PHYSICAL_INTERFACE
sudo systemctl start private-wan-guard-health.service
cat /var/lib/prometheus/node-exporter/textfile/private_wan_guard.prom
```

The interface-specific unit is enabled through the physical device's `.wants` directory. Confirm it, the nft loader and the timer are enabled; verify public access and an authorized private service path. Verify the actual rules, not only `systemctl`'s oneshot state. The monitoring rule detects degraded, stale or missing reporting on scraped hypervisors. Do not run a whole-host reboot solely as a smoke test without an appropriate maintenance window.

Regression rigs must run on an expendable Linux build host with `sudo`, iproute2, nft, ping and Python 3. They create only isolated network namespaces and abort if run in the host network namespace:

```sh
sudo unshare --mount --net ./config/private-wan-guard/test-guard-netns.sh
sudo unshare --mount --net ./config/private-wan-guard/test-health-netns.sh
sudo unshare --mount --net ./config/private-wan-guard/test-hairpin-netns.sh
```

The first rig tests a reachable private peer, then block, public pass, survival of a full nftables flush, idempotence and rollback. The second removes both guard layers and checks restoration and reporting. To roll back only the TC layer, stop the timer and TC service, then run `wan-guard-tc.sh remove PHYSICAL_INTERFACE`; this never deletes the shared qdisc or nftables rules. Document and replace any removed protection immediately.

For a host whose public web ingress reaches an edge guest on the same private subnet, the canonical Proxmox network template also routes private-subnet requests to that host's public IPv4 TCP 80/443 to the private edge. Same-subnet replies are SNATed to the private gateway; the edge sees that gateway as the client for these hairpin connections. The `test-hairpin-netns.sh` rig renders the actual template and tests baseline, repaired path, direct private access and rollback without touching host networking.
