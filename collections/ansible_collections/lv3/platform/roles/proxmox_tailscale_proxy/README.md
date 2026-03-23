# proxmox_tailscale_proxy

Creates systemd socket-activated TCP proxies bound to the host Tailscale address.

Inputs: `platform_host.network.tailscale_tcp_proxies` when generated platform vars are present, otherwise `proxmox_tailscale_tcp_proxies`.
Outputs: rendered socket and service units plus enabled proxy listeners for each declared proxy.
