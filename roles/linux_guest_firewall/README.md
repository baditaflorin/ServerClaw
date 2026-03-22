# linux_guest_firewall

Applies the guest-side nftables policy derived from the canonical `network_policy` inventory data.

Inputs: `network_policy` from `inventory/host_vars/proxmox_florin.yml`.

Outputs: a managed `/etc/nftables.conf`, active nftables service state, and a verified post-reload SSH reconnect path.
