# proxmox_network

Applies the Proxmox host bridge, NAT, and nftables network baseline.

Inputs: management interface settings, bridge names, internal network values, and ingress-forwarding topology.
Outputs: `/etc/network/interfaces`, `/etc/nftables.conf`, and active forwarding/NAT state.
