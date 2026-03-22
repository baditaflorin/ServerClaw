# proxmox_tailscale

Installs Tailscale on the Proxmox host and manages the subnet-router helper.

Inputs: Tailscale apt repository settings, host naming, advertised routes, auth key environment variable name, and Tailscale behavior flags.
Outputs: installed Tailscale packages and a managed `/usr/local/sbin/lv3-tailscale-up` helper.
