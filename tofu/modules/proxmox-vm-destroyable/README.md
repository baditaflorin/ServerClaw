# proxmox-vm-destroyable

Destroyable OpenTofu module for Proxmox VM lifecycle management.

This module intentionally mirrors the shared `proxmox-vm` interface and behavior,
but sets `lifecycle.prevent_destroy = false` so ephemeral fixtures can be created
and torn down without changing the protected production module contract.
