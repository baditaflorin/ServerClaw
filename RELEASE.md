# Release 0.179.49

- Date: 2026-06-09

## Summary
- Add `claude-ops` dedicated AI-automation admin identity: passwordless sudo + key-only SSH on the Proxmox host and all 18 lv3 guest VMs, `claude-ops@pam` with PVEAdmin, and a privilege-separated Proxmox API token (`claude-ops-automation@pve`) — independently auditable and revocable from the shared `ops` account
- Complete the 0mpc.com → 0mcp.com operator-apex migration: regenerate platform.yml and discovery artifacts against the renamed domain, update the sanitization BLOCKED list, and refresh the subdomain exposure registry
- Add the `lv3.platform.uptime_kuma_provision` role (monitors + public status page) with a `provision-uptime-kuma` Make target and playbook wiring
- Fix the bare-root `https://status.<domain>/` 404 by deriving the edge `root_proxy_path` status slug from `platform_domain` instead of a stale literal
- Deploy Woodpecker CI (ci.0mcp.com): fix OpenBao remote address for docker-runtime, add port 3003 Proxmox firewall rule for docker-runtime → runtime-control, bootstrap Gitea OAuth and seed repository

## Platform Impact
- no live platform version bump; this release updates repository automation, release metadata, and operator tooling only

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
