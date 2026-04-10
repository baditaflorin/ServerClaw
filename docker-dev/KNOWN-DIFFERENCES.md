# Known Differences: Docker Dev vs Production

**ADR:** 0387

This document lists known behavioral differences between the Docker
development environment and a real Proxmox production deployment.

## Infrastructure

| Feature | Production | Docker Dev |
|---------|-----------|------------|
| Hypervisor | Proxmox VE with KVM | None (containers) |
| VM isolation | Full kernel isolation | Container namespace isolation |
| Networking | vmbr bridges, VLAN tags | Docker bridge network |
| Storage | LVM-thin, ZFS, NFS | Docker volumes |
| Firewall | pve-firewall + ufw | Not available |
| systemd | Full init system | Not available (SSH is PID 1) |

## Services

| Feature | Production | Docker Dev |
|---------|-----------|------------|
| Proxmox API | Available at :8006 | Skipped (`platform_skip_proxmox_api`) |
| Tailscale/Headscale | VPN mesh | Not available |
| step-ca certificates | Real CA chain | Self-signed or skipped |
| DNS split-horizon | CoreDNS + public DNS | Docker DNS only |
| systemd timers | Used for cron jobs | Replaced by crond or skipped |
| ufw firewall rules | Enforced | Skipped in docker-dev mode |
| Backup (PBS) | Proxmox Backup Server | Mock or skipped |

## Role Compatibility

Roles check `platform_environment` to adapt behavior:

```yaml
# Skip firewall rules in docker-dev
- name: Configure ufw
  when: platform_environment | default('production') != 'docker-dev'
  ...

# Skip Proxmox API calls
- name: Query Proxmox API
  when: not (platform_skip_proxmox_api | default(false))
  ...
```

## What Works Well in Docker Dev

- Ansible convergence of Docker Compose services
- Service-to-service communication over the 10.10.10.0/24 network
- PostgreSQL database operations
- Keycloak SSO (with self-signed certs)
- OpenBao secret management
- Nginx reverse proxy
- Most application services (Dify, Gitea, n8n, etc.)

## What Does Not Work

- Proxmox VM provisioning (no hypervisor)
- Backup and recovery workflows (no PBS)
- Host-level metrics (no real OS to monitor)
- Network policy enforcement (no firewall)
- Certificate authority chain (step-ca needs adaptation)
- GPU workloads (Ollama, inference) — unless GPU passthrough is configured
