# WS-20261029: Keep the agent-history store out of the all_guests fan-out

## Status

In progress. The pull request is open and not merged; nothing is applied. No `[live-apply]` marker.

## Goal

The NetpolicyDrift alert for VM 155 and VM 192 has fired since the store was provisioned. `all_guests` rules expand to every other guest, which now includes the store: re-rendering `runtime-control` gave 10.10.10.55 six NATS, Mailpit, Redpanda, n8n and directus ports (and a forward accept), and the same expansion would add it to many ports on VMs 110, 120, 130 and 140 in the Proxmox files. The store holds every secret an agent ever saw and has no business reaching them. Separately, VM 155's forward chain (Docker host) was not declared in the netpolicy file, and the scoped firewall render needs an override that nothing documents.

## Change

- `inventory/host_vars/proxmox-host.yml`: `network_policy_all_guests: false` on vmid 155 (default `true` for every guest); the stale comment that the guest was not provisioned is corrected.
- `linux_guest_firewall` (`tasks/main.yml`, `templates/nftables.conf.j2`) and `proxmox_network` (`templates/vm.fw.j2`): `all_guests` expansion skips guests with the flag, in the guest nftables input and forward chains and in the Proxmox VM firewall files. Named-source rules (`source: agent-history`, OpenBao tcp 8201 on runtime-control) are untouched. `scripts/firewall_drift.py`, which mirrors both templates, skips them too.
- `config/network-policy/0mcp.yaml`: VM 155 declares the `forward` layer (its input flows are mirrored into the forward chain by the role, plus the three Docker container ranges that the docker_runtime role puts there, as on VM 170); VM 192's forward group names 10.10.10.55, which the explicit OpenBao rule renders. `scripts/netpolicy.py check` passes unchanged.
- `tests/test_network_policy_all_guests_flag.py` (9 tests, mutation-checked against each renderer, the drift tool and the inventory flag), including that VM 155's rendered `155.fw` equals what the netpolicy file declares.
- `docs/runbooks/configure-guest-network-policy.md`: the 0mcp invocation of the scoped slice with `-e management_interface=enp7s0` and why the guard stays; a section on the flag. `docs/runbooks/configure-agent-history.md`: the claim that a full run adds six all_guests ports is corrected.

Applying it is the owner's: land this, run the scoped slice (creates 155.fw), re-render runtime-control's guest nftables, then `scripts/netpolicy.py drift --live`.
