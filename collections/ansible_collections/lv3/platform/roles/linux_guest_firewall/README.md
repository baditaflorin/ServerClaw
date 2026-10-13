# linux_guest_firewall

Applies the guest-side nftables policy derived from the canonical `network_policy` inventory data.

Inputs: `network_policy` from `inventory/host_vars/proxmox-host.yml`.

Outputs: a managed `/etc/nftables.conf` covering local services and forwarded container ports, active nftables service state, and a verified post-reload SSH reconnect path. Guests may opt into narrowly scoped container SNAT for private-edge HTTPS or explicit source/destination/protocol/port tuples; this does not grant general container egress.
