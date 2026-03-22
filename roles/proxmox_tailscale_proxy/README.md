# proxmox_tailscale_proxy

Creates systemd socket-activated TCP proxies bound to the host Tailscale address.

Inputs: `proxmox_tailscale_tcp_proxies`.
Outputs: rendered socket and service units plus enabled proxy listeners for each declared proxy.
