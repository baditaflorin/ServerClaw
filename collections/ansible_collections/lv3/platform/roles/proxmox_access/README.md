# proxmox_access

Applies the Linux host access baseline and provisions the Proxmox PAM admin identity.

Inputs: Proxmox host admin identity fields and SSH hardening path.
Outputs: the Linux admin user plus the corresponding `@pam` Proxmox identity with `PVEAdmin`.
