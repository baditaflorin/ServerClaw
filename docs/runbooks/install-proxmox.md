# Install Proxmox Runbook

## Purpose

This runbook captures the executable path used to install Proxmox VE on the Debian 13 host from this repository.

## Preconditions

- Debian 13 is already installed on the target host.
- SSH access works with the bootstrap key.
- The inventory entry for the host is up to date.

## Commands

Syntax check:

```bash
make syntax-check
```

Apply:

```bash
make install-proxmox
```

## What the playbook does

1. Validates the target is Debian 13.
2. Adds the official Proxmox package repository.
3. Installs the Proxmox kernel and `ifupdown2`.
4. Reboots into the Proxmox kernel.
5. Installs `proxmox-ve`, `postfix`, `open-iscsi`, and `chrony`.
6. Removes `linux-image-amd64` and `os-prober`.
7. Verifies the installed Proxmox version.

## Latest observed result

Observed on 2026-03-21:

```text
proxmox-ve: 9.1.0
pve-manager: 9.1.6
running kernel: 6.17.13-2-pve
```

## Notes

- This runbook does not yet convert the Hetzner routed NIC into a Proxmox bridge.
- This runbook does not yet apply the full SSH, firewall, TLS, or TFA hardening baseline.
