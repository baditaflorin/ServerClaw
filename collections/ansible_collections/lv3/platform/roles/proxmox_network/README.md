# proxmox_network

Applies the Proxmox host bridge, NAT, nftables, and per-VM firewall baseline.

Inputs: management interface settings, bridge names, internal network values, ingress-forwarding topology, guest inventory, and canonical `network_policy` rules. Guest inventory entries may set `proxmox_firewall_enabled: false` when a VM should rely on its in-guest firewall instead of the Proxmox `fwbr*` bridge path.
Outputs: `/etc/network/interfaces`, `/etc/nftables.conf`, `/etc/pve/firewall/<vmid>.fw`, a managed conntrack helper for `fwbr+` traffic, and active forwarding/NAT plus Proxmox VM firewall state.
