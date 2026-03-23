# Break-Glass References

## Purpose

This file records *where* emergency recovery materials live for ADR 0100.

It must never contain actual credentials, unseal keys, private keys, or TOTP seeds.

## Required Materials

- Hetzner account access for server reinstall
- emergency Proxmox host SSH access for `root`
- OpenBao unseal references from ADR 0051
- `step-ca` root fingerprint
- Storage Box access details for the off-site `backup-lv3` recovery copy

## Storage Locations

- Hetzner reinstall access: operator-held external credential store
- Proxmox host break-glass SSH key: external operator-held key store
- OpenBao init and unseal references: controller-local OpenBao artifacts and the ADR 0051 break-glass path
- `step-ca` root fingerprint: current `step-ca` bootstrap materials under `.local/step-ca/`
- Storage Box connection values: external operator-held credential store plus the `PROXMOX_DR_OFFSITE_*` execution environment used for `make configure-backup-vm`

## Operating Rules

- keep the physical or password-manager copy current whenever any break-glass material changes
- do not commit emergency secrets into the repo
- after any break-glass use, rotate the affected credentials and update the external reference copy
