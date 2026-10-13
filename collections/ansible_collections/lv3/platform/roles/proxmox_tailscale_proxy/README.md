# proxmox_tailscale_proxy

Creates systemd socket-activated TCP proxies bound to the host Tailscale address.

Inputs: `platform_host.network.tailscale_tcp_proxies` when generated platform vars are present, otherwise `proxmox_tailscale_tcp_proxies`.
Outputs: rendered socket and service units plus enabled proxy listeners for each declared proxy.

Each socket is wanted by both `sockets.target` and `tailscaled.service`. This
re-arms private listeners after a Tailscale daemon restart, which can
temporarily remove `tailscale0` and stop sockets bound to that device. The role
also checks socket state (not just whether an already-accepted proxy service is
active), starts a missing listener, and asserts that the socket is active at
the end of converge.
