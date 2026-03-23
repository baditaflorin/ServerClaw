# proxmox_ntopng

Installs ntopng on the Proxmox host, captures private-network traffic from the declared interfaces, and verifies the operator-facing REST surface.

Inputs: ntop repository settings, monitored interface names, local-network definitions, admin-password path, and the host Tailscale access URL.
Outputs: managed ntopng packages, repo-owned ntopng config, a generated admin password, and verified interface visibility over the private access path.
