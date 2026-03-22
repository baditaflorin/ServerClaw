# proxmox_network

Applies the Proxmox host bridge, NAT, nftables, and per-VM firewall baseline.

Inputs: management interface settings, bridge names, internal network values, ingress-forwarding topology, guest inventory, and canonical `network_policy` rules.
Outputs: `/etc/network/interfaces`, `/etc/nftables.conf`, `/etc/pve/firewall/<vmid>.fw`, a managed conntrack helper for `fwbr+` traffic, and active forwarding/NAT plus Proxmox VM firewall state.
