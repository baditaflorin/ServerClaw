# WS-20261029: Postgres HA VIP versus the agent-history guest address

## Status

In progress. The pull request is open and not merged; nothing is applied. No `[live-apply]` marker.

## Goal

`postgres_ha.vip_ipv4` has declared 10.10.10.55 as the Postgres HA keepalived VIP since 2026-08-27 (#137). The agent-history guest (vmid 155) was given the same address on 2026-10-28. The VIP is not deployed on 0mcp (checked live by the agent-history session on 2026-10-29: ARP for 10.10.10.55 resolves only to VM 155, keepalived is inactive on VMs 150, 151, 152 and 154, and database.<domain> resolves elsewhere), so nothing broke; but the first Patroni or keepalived deploy, or playbooks/database-dns.yml (service topology `postgres.private_ip` is the VIP), would have put two hosts on one address and pointed the database name at the store.

## Change

- `inventory/host_vars/proxmox-host.yml`: `postgres_ha.vip_ipv4` 10.10.10.55 -> 10.10.10.58 (referenced nowhere else in the repository; the other two declared VIPs, 10.10.10.56 and 10.10.10.57, are unchanged). No live change is needed: the VIP is not deployed. The store keeps 10.10.10.55 (the OpenBao AppRole CIDR binding, `192.fw`, the nft rules and the netpolicy file all carry it).
- `tests/test_guest_addresses_distinct.py` (6 tests, mutation-checked): every `*_ha.vip_ipv4` is distinct, no guest address equals a VIP or another guest's address, the internal host address is neither, the netpolicy file never names a VIP as a VM address or as a VRRP peer (its VRRP groups on VMs 150 and 151 name the peers 10.10.10.50 and 10.10.10.51, checked), and the Postgres VIP is not the store address. They run against the live inventory and the public fork template.
- The public fork template (`publication/templates/proxmox-host.yml`) is unchanged: it has its own guest list and passes the same tests.
