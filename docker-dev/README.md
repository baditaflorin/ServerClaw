# ServerClaw Docker Development Environment

**ADR:** 0387

Run the ServerClaw platform locally using Docker containers as VM stand-ins.
No bare-metal server required.

## Quick Start

```bash
# From the repo root:
make init-local              # Generate SSH keys (first time only)
make docker-dev-up           # Start 4 containers
make docker-dev-verify       # Check SSH connectivity
make docker-dev-converge     # Deploy services via Ansible
```

## Tiers

### Tier 1: Minimal (default)

4 containers, 8 GB RAM, works on ARM Mac.

| Container | IP | Role |
|-----------|-----|------|
| postgres-vm | 10.10.10.50 | Shared PostgreSQL |
| control-plane | 10.10.10.92 | Keycloak, OpenBao, API gateway |
| nginx-edge | 10.10.10.10 | Reverse proxy (host ports 8080/8443) |
| monitoring-vm | 10.10.10.40 | Grafana + Prometheus (opt-in) |

```bash
make docker-dev-up                     # Without monitoring
COMPOSE_PROFILES=monitoring make docker-dev-up  # With monitoring
```

### Tier 2: Full Topology

7 containers, 16-24 GB RAM, works on ARM Mac.

```bash
make docker-dev-up-full
```

Adds: docker-runtime, docker-build, backup-vm, and runtime-control.

## Architecture

Each container runs a `vm-base` image:
- Ubuntu 24.04 with SSH server
- `ops` user with passwordless sudo
- Docker CLI (talks to host Docker via socket mount)
- Python 3 for Ansible

Ansible targets `inventory/hosts-docker.yml` which uses the same IP scheme
as production. The `platform_environment: docker-dev` variable tells roles
to skip Proxmox API calls, firewall rules, and systemd timers.

## Commands

| Command | Description |
|---------|-------------|
| `make docker-dev-up` | Start Tier 1 (minimal) |
| `make docker-dev-up-full` | Start Tier 2 (full topology) |
| `make docker-dev-down` | Stop all containers |
| `make docker-dev-verify` | Check SSH connectivity |
| `make docker-dev-converge` | Run Ansible against containers |
| `make docker-dev-reset` | Destroy and recreate |

## Known Differences from Production

See [KNOWN-DIFFERENCES.md](KNOWN-DIFFERENCES.md).

## Host Port Mapping

| Host Port | Container | Service |
|-----------|-----------|---------|
| 8080 | nginx-edge | HTTP |
| 8443 | nginx-edge | HTTPS |

## Troubleshooting

**"Cannot connect to Docker daemon"**

Ensure Docker Desktop / Docker Engine is running.

**"SSH connection refused"**

Wait 10 seconds after `docker-dev-up` for SSH to start, then retry.

**"No such file: .local/ssh/bootstrap.id_ed25519.pub"**

Run `make init-local` first to generate SSH keys.

**Container exits immediately**

Check logs: `docker logs serverclaw-postgres-vm`
