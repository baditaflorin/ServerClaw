# Harden Access Runbook

## Purpose

This runbook captures the executable path used to reduce root-centric SSH access on the Proxmox host and Debian guests.

## Result

- creates non-root host admin user `ops`
- installs the repository bootstrap public key for `ops`
- grants passwordless sudo to `ops`
- disables SSH password authentication
- keeps `root` as key-only break-glass access
- creates `ops@pam` in Proxmox with `PVEAdmin`
- makes `ops` the default automation identity for the Proxmox host
- enforces key-only, no-root SSH on the guest VMs
- retains the Proxmox host jump path only as the guest break-glass fallback after ADR 0014

## Command

```bash
make harden-access
make harden-guest-access
```

## Verification

Host shell:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1
sudo -n pveversion
```

Guest shell via host jump break-glass fallback:

```bash
ssh -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 -W %h:%p' \
  -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  ops@10.10.10.30
```

Steady-state guest access is documented in [Configure Tailscale Private Access](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/configure-tailscale-access.md).

Ansible host verification:

```bash
ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml proxmox_hosts -m command -a 'id' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519
ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml lv3_guests -m command -a 'id' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519
```
