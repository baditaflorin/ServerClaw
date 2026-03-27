# proxmox_guests

Clones the managed guest VM set from the repo-managed Proxmox template catalog.

Inputs: Proxmox template metadata, storage and bridge settings, and the `proxmox_guests` inventory data.
Outputs: cloud-init snippets plus converged guest VM hardware and network settings cloned from the declared template source.
