# Complete Security Baseline Runbook

## Purpose

This runbook captures the executable path used to complete the Proxmox host security baseline defined in ADR 0006.

## Result

- Proxmox host firewall enabled with management access restricted to declared source ranges
- routine host administration expected over the Proxmox Tailscale IP instead of a location-specific public-IP allowlist
- `ops@pam` protected by TOTP
- ACME certificate issued for `proxmox.example.com`
- notification endpoint and catch-all matcher configured

## Command

```bash
HETZNER_DNS_API_TOKEN=... make harden-security
```

## Current implementation details

- Management firewall source ranges are defined in [inventory/group_vars/all.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/group_vars/all.yml).
- The steady-state management source is the Tailscale CGNAT range, with the host reached on `100.118.189.95`.
- The ACME certificate uses the Hetzner DNS plugin and the `proxmox.example.com` hostname.
- Notifications currently use a sendmail endpoint to `operator@example.com`.
- TOTP material for `ops@pam` is generated locally and stored outside git in:
  `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/tfa/proxmox-ops-pam-totp.json`

## Verification

Firewall policy:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 'sudo pve-firewall status'
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'hostname && sudo pve-firewall status'
```

Certificate:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 'sudo pvenode cert info --output-format json-pretty'
```

TFA:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 'sudo pvesh get /access/tfa/ops@pam --output-format json-pretty'
```

Notifications:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 'sudo pvesh get /cluster/notifications/endpoints/sendmail --output-format json-pretty'
```
