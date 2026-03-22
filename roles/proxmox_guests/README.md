# proxmox_guests

Creates the Debian cloud template and the managed guest VM set.

Inputs: cloud image metadata, Proxmox template/storage settings, bridge settings, and the `proxmox_guests` inventory data.
Outputs: a template VM, cloud-init snippets, and converged guest VM hardware and network settings.
