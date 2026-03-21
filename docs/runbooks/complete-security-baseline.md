# Complete Security Baseline Runbook

## Purpose

This runbook captures the executable path used to complete the Proxmox host security baseline defined in ADR 0006.

## Result

- Proxmox host firewall enabled with management access restricted to declared source ranges
- `ops@pam` protected by TOTP
- ACME certificate issued for `proxmox.lv3.org`
- notification endpoint and catch-all matcher configured

## Command

```bash
HETZNER_DNS_API_TOKEN=... make harden-security
```

## Current implementation details

- Management firewall source ranges are defined in [inventory/group_vars/all.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/group_vars/all.yml).
- The ACME certificate uses the Hetzner DNS plugin and the `proxmox.lv3.org` hostname.
- Notifications currently use a sendmail endpoint to `baditaflorin@gmail.com`.
- TOTP material for `ops@pam` is generated locally and stored outside git in:
  `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/tfa/proxmox-ops-pam-totp.json`

## Verification

Firewall policy:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@65.108.75.123 'sudo pve-firewall status'
```

Certificate:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@65.108.75.123 'sudo pvenode cert info --output-format json-pretty'
```

TFA:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@65.108.75.123 'sudo pvesh get /access/tfa/ops@pam --output-format json-pretty'
```

Notifications:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@65.108.75.123 'sudo pvesh get /cluster/notifications/endpoints/sendmail --output-format json-pretty'
```
