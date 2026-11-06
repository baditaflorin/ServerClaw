# dockerhost-neigh-gc: kernel neighbour (ARP) table thresholds for a Docker host with ~460 containers

Installed on the 0docker dockerhost VM (`ubuntuvm1`, 10.10.10.20, kernel 6.8). The VM is not managed by Ansible or fleet-runner, so this
directory is the source of truth: change the file here through a PR, then install it as below.

## What it does and why
All network namespaces share ONE kernel neighbour table per protocol. `net.ipv4.neigh.default.gc_thresh{1,2,3}` exist only in the
init-netns `default` directory (there is nothing per bridge, per interface or per container to set), and they limit the sum over the host
and every container netns. Defaults are 128 / 512 / 1024.

Measured 2026-10-18 06:45-07:00Z (`/proc/net/stat/arp_cache`, hex columns, summed over CPUs):

| Where | Entries |
|---|---|
| host netns (`ip -4 neigh`) | about 410, of which about 220 on `pentest_network` (172.21.0.0/16, 384 containers). Prometheus runs with host networking and reaches container IPs directly; plus docker-proxy |
| container netns (459 of them, via `nsenter --net=/run/docker/netns/<id> cat /proc/net/arp`) | about 540 |
| kernel total | 940 to 1022 (capped by gc_thresh3), 1360 to 1390 once the cap was lifted |

Effect with the defaults: the table sits above gc_thresh2 permanently, so every ~5 s of allocation pressure runs a forced GC that deletes
about 100 live entries (`forced_gc_runs` 115k, `destroys` about 100 per forced run); they are re-resolved immediately (ARP broadcast, 15-85
allocations per second in bursts). It is also within 3% of gc_thresh3, so any burst (for example fleet-runner deploy activity, the 30 s
Prometheus scrape cycle, the daily 02:00Z scanopy discovery session) logs `neighbour: arp_cache: neighbor table overflow!` (`table_fulls`
4636 since boot; 50 to 175 log lines per hour since 2026-10-17 about 16:00Z). That is when the working set crossed the limit: Prometheus
targets grew from 513 (2026-10-17 10:00Z) to 604 (16:00Z) to 693 (2026-10-18 00:00Z) as services and replicas were added.
There were no FAILED or INCOMPLETE entries (396 REACHABLE, 6 STALE, 6 DELAY), so no scanner sweeping non-existent addresses.

New values: 2048 / 4096 / 8192 for ipv4 and ipv6 (ipv6 is disabled on this host today; set for symmetry and future-proofing). gc_thresh3 is
about 6x the unconstrained working set, gc_thresh2 about 3x. Cost is about 0.3 KB per entry.

| File here | Live path | Owner, mode |
|---|---|---|
| `90-fleet-neigh-gc.conf` | `/etc/sysctl.d/90-fleet-neigh-gc.conf` | root:root 0644 |

## Install
```
sudo install -o root -g root -m 0644 90-fleet-neigh-gc.conf /etc/sysctl.d/90-fleet-neigh-gc.conf
sudo sysctl -p /etc/sysctl.d/90-fleet-neigh-gc.conf
```
Applied live 2026-10-18 06:56Z. Before: `sysctl -a` snapshot and a tar of `/etc/sysctl.d` were kept in `/var/backups/arp-fix-20261018T065539Z/`
on the VM. A full `sysctl -a` diff before and after showed only the six keys changed (plus volatile counters).

## Verify
```
sysctl net.ipv4.neigh.default.gc_thresh1 net.ipv4.neigh.default.gc_thresh2 net.ipv4.neigh.default.gc_thresh3
awk 'NR>1{e=strtonum("0x"$1); tf+=strtonum("0x"$NF); fg+=strtonum("0x"$(NF-2))} END{print "entries="e, "table_fulls="tf, "forced_gc_runs="fg}' /proc/net/stat/arp_cache
sudo journalctl -k --since -1h | grep -c 'neighbor table overflow'
```
`forced_gc_runs` and `table_fulls` must stop increasing. Raise the values again if `entries` approaches `gc_thresh2` (4096), for
example if the container count on the VM doubles.

## Rollback
Delete the file, then `sudo sysctl -w net.ipv4.neigh.default.gc_thresh3=1024 net.ipv4.neigh.default.gc_thresh2=512 net.ipv4.neigh.default.gc_thresh1=128`
and the same for `net.ipv6.neigh.default`.

## Owner-side notes (not changed here)
- Prometheus in host network mode scrapes container bridge IPs directly, so the host netns holds one entry per scraped container. That is
  expected and now fits.
- `scanopy-daemon` (systemd, root) runs a 25-30 minute discovery session every day at 02:00:22Z: it probes every container IP and
  sweeps ARP on each veth, which toggles `ens18` into promiscuous mode for seconds (the `virtio_net ... ens18: entered promiscuous mode`
  lines at 02:01Z). It added to the overflow before this change; with the new limits it is harmless.
