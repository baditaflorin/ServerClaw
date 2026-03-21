# Configure Proxmox Network Runbook

## Purpose

This runbook captures the executable path used to convert the host from the Hetzner installimage NIC configuration into a Proxmox bridge layout.

## Resulting topology

- `vmbr0`: public management bridge using `enp7s0`
- `vmbr10`: private internal bridge on `10.10.10.1/24`
- IPv4 forwarding: enabled
- outbound NAT for `10.10.10.0/24`: enabled with `nftables`

## Command

```bash
make configure-network
```

## What the playbook does

1. Removes the unauthorized Proxmox enterprise repository when running on `pve-no-subscription`.
2. Installs and enables `nftables`.
3. Enables `net.ipv4.ip_forward`.
4. Rewrites `/etc/network/interfaces` to a Proxmox bridge layout.
5. Loads the NAT ruleset for guest egress.
6. Applies the bridge configuration with `ifreload -a`.
7. Waits for SSH to return.

## Latest observed result

Observed on 2026-03-21:

```text
vmbr0 -> public bridge on enp7s0
vmbr10 -> 10.10.10.1/24
net.ipv4.ip_forward = 1
nft masquerade for 10.10.10.0/24 via vmbr0
```
