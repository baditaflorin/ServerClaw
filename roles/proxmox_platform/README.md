# proxmox_platform

Installs the Proxmox VE package baseline on the host.

Inputs: host public hostname, core package list, and cleanup package list.
Outputs: installed Proxmox packages and removed Debian kernel meta packages that conflict with the target baseline.
