# proxmox_repository

Configures the Proxmox Debian repository path and upgrades the base system.

Inputs: Debian prerequisite packages, Proxmox repository metadata, and archive key settings.
Outputs: the repository source file, keyring, updated apt cache, and a dist-upgraded Debian base.
