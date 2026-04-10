# ServerClaw Platform

Forkable infrastructure-as-code for taking a bare Debian 13 server to a
fully managed Proxmox VE platform with 70+ self-hosted services — deployed,
monitored, and recoverable from a single repository.

## Quick Start

### Try it locally (Docker, no server needed)

```bash
git clone https://github.com/baditaflorin/proxmox_florin_server.git
cd proxmox_florin_server
make init-local              # Generate SSH keys and secrets
make docker-dev-up           # Start 4 containers (8 GB RAM, ARM Mac native)
make docker-dev-converge     # Deploy services via Ansible
```

See [docker-dev/README.md](docker-dev/README.md) for details.

### Deploy to a real server

```bash
git clone https://github.com/baditaflorin/proxmox_florin_server.git
cd proxmox_florin_server
make init-local              # Generate SSH keys and 237 service secrets
# Edit inventory/hosts.yml and inventory/group_vars/all/identity.yml
make bootstrap               # Full staged bootstrap with validation gates
```

See [docs/runbooks/bootstrap-from-scratch.md](docs/runbooks/bootstrap-from-scratch.md)
for the complete walkthrough.

## What This Is

A single Git repository that contains everything needed to operate a
self-hosted platform:

| Layer | What | Count |
|-------|------|-------|
| Architecture decisions | `docs/adr/` | 420+ ADRs |
| Ansible roles | `collections/ansible_collections/lv3/platform/roles/` | 165 roles |
| Playbooks | `collections/ansible_collections/lv3/platform/playbooks/` | 111 playbooks |
| Operational runbooks | `docs/runbooks/` | 267 runbooks |
| Automation scripts | `scripts/` | 293 scripts |
| Validation tests | `tests/` | Automated regression suite |

### Services included

SSO (Keycloak), secrets (OpenBao), databases (PostgreSQL), reverse proxy (Nginx),
monitoring (Grafana + Prometheus), CI/CD (Woodpecker, Semaphore), Git hosting (Gitea),
object storage (MinIO), container registry (Harbor), AI/LLM (Ollama, Dify, LiteLLM,
LibreChat, Open WebUI), project management (Plane, Vikunja), communication
(Mattermost, Matrix), wiki (Outline), analytics (Plausible, Superset), workflow
automation (n8n, Windmill, Temporal), and many more.

## Forking This Repo

The platform is designed to be forked. One file controls your identity:

```bash
# inventory/group_vars/all/identity.yml — the ONLY file you must edit to rebrand
platform_domain: yourdomain.com
platform_operator_email: you@yourdomain.com
platform_operator_name: "Your Name"
```

Everything else derives from these values via Ansible templating.

### Fork checklist

1. Edit `inventory/group_vars/all/identity.yml` (domain, name, email)
2. Copy `inventory/hosts.yml.example` to `inventory/hosts.yml` and customize
3. Run `make init-local` to generate secrets
4. Choose a [provider profile](config/provider-profiles/) (Hetzner, generic Debian, homelab)
5. Run `make bootstrap` or `make docker-dev-up`

See [docs/runbooks/bootstrap-from-scratch.md](docs/runbooks/bootstrap-from-scratch.md).

## Development Environment

Three tiers, all using Docker containers as VM stand-ins:

| Tier | Containers | RAM | ARM Mac | What works |
|------|-----------|-----|---------|------------|
| Minimal | 4 (PG, control, nginx, monitoring) | 8 GB | native | SSO, secrets, DB, proxy |
| Full | 7 (all VMs) | 16 GB | native | All services |
| Proxmox | 1 QEMU host | 32 GB | x86 only | Full PVE bootstrap |

```bash
make docker-dev-up           # Tier 1
make docker-dev-up-full      # Tier 2
make docker-dev-converge     # Run Ansible against containers
make docker-dev-down         # Cleanup
```

## Architecture

```
Proxmox VE Host (Debian 13, bare metal)
  |
  +-- nginx-edge        (10.10.10.10)  Reverse proxy, TLS termination
  +-- docker-runtime    (10.10.10.20)  Primary application runtime
  +-- docker-build      (10.10.10.30)  CI/CD build server
  +-- monitoring        (10.10.10.40)  Grafana, Prometheus, Alertmanager
  +-- postgres          (10.10.10.50)  Shared PostgreSQL 16
  +-- backup            (10.10.10.60)  Proxmox Backup Server
  +-- runtime-control   (10.10.10.92)  API gateway, agent tools
  +-- runtime-ai        (10.10.10.90)  GPU workloads (Ollama, inference)
  +-- [additional VMs per topology]
```

All guest VMs are managed declaratively. The Ansible inventory defines the
topology; `make provision-guests` creates VMs via the Proxmox API.

## Key Concepts

- **Identity isolation**: All operator-specific values live in one file
  (`identity.yml`). Zero hardcoded domains or hostnames in role code.
- **Secret management**: 260 secrets documented in `config/controller-local-secrets.json`.
  `.local/` directory holds runtime secrets (never committed).
  `make init-local` generates everything from the manifest.
- **Derive, don't declare**: `derive_service_defaults` computes 15-25
  variables per service from a registry — roles don't repeat boilerplate.
- **ADR governance**: Every architectural decision is recorded and indexed.
  Pre-commit hooks enforce status transitions.
- **Verification gates**: `make verify-bootstrap-proxmox`, `make verify-bootstrap-guests`,
  `make verify-platform` validate state between stages.

## Repository Structure

```
.
├── collections/ansible_collections/lv3/platform/
│   ├── roles/           # 165 Ansible roles
│   ├── playbooks/       # 111 playbooks
│   └── plugins/         # Custom filters and callbacks
├── inventory/
│   ├── hosts.yml        # Your deployment topology
│   ├── hosts.yml.example # Fork template
│   ├── hosts-docker.yml # Docker dev inventory
│   └── group_vars/      # Platform configuration
├── config/
│   ├── provider-profiles/  # Bootstrap profiles per hosting provider
│   └── controller-local-secrets.json  # Secret manifest
├── docker-dev/          # Docker development environment
│   ├── images/vm-base/  # Container-as-VM base image
│   ├── minimal/         # Tier 1 compose (4 containers)
│   └── full/            # Tier 2 compose (7 containers)
├── docs/
│   ├── adr/             # 420+ architecture decision records
│   └── runbooks/        # 267 operational runbooks
├── scripts/             # 293 automation scripts
├── local-overlay-template/  # Scaffold for .local/ secrets directory
└── Makefile             # 200+ automation targets
```

Full layout: [.repo-structure.yaml](.repo-structure.yaml)

## Make Targets

| Target | Description |
|--------|-------------|
| `make init-local` | Generate `.local/` with SSH keys and secrets |
| `make bootstrap` | Full staged bootstrap (Proxmox + guests + convergence) |
| `make bootstrap-minimal` | Critical path only (PG + Keycloak + Nginx + OpenBao) |
| `make docker-dev-up` | Start Docker dev environment (Tier 1) |
| `make docker-dev-converge` | Deploy to Docker containers |
| `make converge-<service>` | Deploy a specific service |
| `make verify-platform` | Health check all critical services |
| `make validate` | Run full validation suite |

## Documentation

| Resource | Location |
|----------|----------|
| Bootstrap guide | [docs/runbooks/bootstrap-from-scratch.md](docs/runbooks/bootstrap-from-scratch.md) |
| ADR index | [docs/adr/.index.yaml](docs/adr/.index.yaml) |
| Runbooks | [docs/runbooks/](docs/runbooks/) |
| Docker dev guide | [docker-dev/README.md](docker-dev/README.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Agent guide | [AGENTS.md](AGENTS.md) |
| Release notes | [docs/release-notes/README.md](docs/release-notes/README.md) |
| Changelog | [changelog.md](changelog.md) |

## Requirements

**For Docker development (Tier 1):**
- Docker Desktop or Docker Engine
- 8 GB free RAM
- macOS (ARM or Intel), Linux, or WSL2

**For production deployment:**
- Dedicated x86_64 server with Debian 13
- 32 GB RAM, 500 GB disk
- Python 3.12+, Ansible, `uv` (Python package manager)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow, ADR governance,
and merge procedures.
