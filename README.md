<!-- =============================================================================
     GENERATED — do not edit README.md directly.

     Source:    docs/templates/README.md.j2
     Generator: scripts/generate_readme.py  (run: make generate-readme)
     Check:     make validate-generated-readme

     Human-readable prose lives in the template.
     Dynamic blocks injected at render time (Jinja2 variables):
       counts.*            — directory/file counts (roles, ADRs, runbooks, …)
       make_targets_table  — parsed from Makefile '## ' comment annotations
       generated_on        — ISO date of last render

     To add a target to the Make Targets table:
       1. Annotate the Makefile target with '## Description'
       2. Add the target name to KEY_MAKE_TARGETS in scripts/generate_readme.py
       3. Run: make generate-readme
     ============================================================================= -->

# ServerClaw Platform

Forkable infrastructure-as-code for taking a bare Debian 13 server to a
fully managed Proxmox VE platform with 75+ self-hosted services — deployed,
monitored, and recoverable from a single repository.

## Quick Start

### Try it locally (Docker, no server needed)

```bash
git clone https://github.com/baditaflorin/ServerClaw.git
cd ServerClaw
make init-local              # Generate SSH keys and secrets
make docker-dev-up           # Start 4 containers (8 GB RAM, ARM Mac native)
make docker-dev-converge     # Deploy services via Ansible
```

See [docker-dev/README.md](docker-dev/README.md) for details.

### Deploy to a real server

```bash
git clone https://github.com/baditaflorin/ServerClaw.git
cd ServerClaw
make init-local              # Generate SSH keys and secrets
make generate-inventory      # Generate inventory/hosts.yml from the platform host vars source
# Edit inventory/group_vars/all/identity.yml (domain, operator name/email)
make bootstrap               # Full staged bootstrap with validation gates
```

See [docs/runbooks/bootstrap-from-scratch.md](docs/runbooks/bootstrap-from-scratch.md)
for the complete walkthrough.

## AI-Native Infrastructure

This platform is built for AI-assisted operations. Every architectural decision,
deployment procedure, and operational runbook is written so that AI coding
assistants (Claude Code, GPT, Codex) can read, understand, and execute them.

- **[CLAUDE.md](CLAUDE.md)** — Claude Code session protocol with checklists and context
- **[AGENTS.md](AGENTS.md)** — Multi-agent coordination rules and handoff protocol
- **443+ ADRs** — Every architectural decision documented and indexed
- **269+ runbooks** — Step-by-step procedures an AI agent can follow
- **Workstream tracking** — Parallel agent sessions coordinate via YAML manifests

Point Claude Code at this repo and it knows how to deploy, debug, and extend
every service.

## What This Is

A single Git repository that contains everything needed to operate a
self-hosted platform:

| Layer | What | Count |
|-------|------|-------|
| Architecture decisions | `docs/adr/` | 443+ ADRs |
| Ansible roles | `collections/ansible_collections/lv3/platform/roles/` | 160 roles |
| Playbooks | `collections/ansible_collections/lv3/platform/playbooks/` | 61 playbooks |
| Operational runbooks | `docs/runbooks/` | 269+ runbooks |
| Automation scripts | `scripts/` | 307+ scripts |
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

```yaml
# inventory/group_vars/all/identity.yml — the ONLY file you must edit to rebrand
platform_domain: yourdomain.com
platform_operator_email: you@yourdomain.com
platform_operator_name: "Your Name"
```

Everything else derives from these values via Ansible templating.

### Fork checklist

1. Edit `inventory/group_vars/all/identity.yml` (domain, name, email)
2. Run `make generate-inventory` — generates `inventory/hosts.yml` from `inventory/host_vars/<platform-host>.yml`
3. Run `make init-local` to generate secrets
4. Choose a [provider profile](config/provider-profiles/) (cloud, generic Debian, or homelab)
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
  +-- nginx-edge        (10.0.0.10)  Reverse proxy, TLS termination
  +-- docker-runtime    (10.0.0.20)  Primary application runtime
  +-- docker-build      (10.0.0.30)  CI/CD build server
  +-- monitoring        (10.0.0.40)  Grafana, Prometheus, Alertmanager
  +-- postgres          (10.0.0.50)  Shared PostgreSQL 16
  +-- backup            (10.0.0.60)  Proxmox Backup Server
  +-- runtime-control   (10.0.0.90)  API gateway, agent tools
  +-- runtime-ai        (10.0.0.92)  GPU workloads (Ollama, inference)
  +-- [additional VMs per topology]
```

All guest VMs are managed declaratively. `inventory/host_vars/<platform-host>.yml`
is the single source of truth for VM topology (VMID, IP, RAM, cores). Running
`make generate-inventory` derives `inventory/hosts.yml` and all Ansible host
variables from it — no manual IP editing.

## Key Concepts

- **Identity isolation**: All operator-specific values live in one file
  (`identity.yml`). Zero hardcoded domains or hostnames in role code.
- **Secret management**: Secrets documented in `config/controller-local-secrets.json`.
  `.local/` directory holds runtime secrets (never committed).
  `make init-local` generates everything from the manifest.
- **Derive, don't declare**: `derive_service_defaults` computes 15-25
  variables per service from a registry — roles don't repeat boilerplate.
- **Generated inventory**: `inventory/hosts.yml` is machine-generated from
  `proxmox_guests` in the platform host vars source file. Edit the source, not the output.
- **ADR governance**: Every architectural decision is recorded and indexed.
  Pre-commit hooks enforce status transitions.
- **Verification gates**: `make verify-bootstrap-proxmox`, `make verify-bootstrap-guests`,
  `make verify-platform` validate state between stages.
- **Static analysis gate**: Three blocking checks run without Docker on every push —
  cross-catalog referential integrity (`validate_cross_catalog_integrity.py`),
  Python type-safety + bandit SAST (`make validate-types`), and
  Z3 formal proofs of the waiver escalation state machine (`verify_waiver_escalation.py`).
  See [docs/runbooks/validation-gate.md](docs/runbooks/validation-gate.md) for details.

## Repository Structure

```
.
├── collections/ansible_collections/lv3/platform/
│   ├── roles/           # 160 Ansible roles
│   ├── playbooks/       # 61 playbooks
│   └── plugins/         # Custom filters and callbacks
├── inventory/
│   ├── hosts.yml        # GENERATED — see scripts/generate_inventory.py
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
│   ├── adr/             # 443+ architecture decision records
│   ├── runbooks/        # 269+ operational runbooks
│   └── templates/       # Jinja2 templates for generated docs (incl. this README)
├── scripts/             # 307+ automation scripts
├── local-overlay-template/  # Scaffold for .local/ secrets directory
└── Makefile             # 27+ automation targets
```

Full layout: [.repo-structure.yaml](.repo-structure.yaml)

## Make Targets

<!-- Generated from Makefile '## ' annotations by scripts/generate_readme.py -->
| Target | Description |
|--------|-------------|
| `make init-local` | Initialize .local/ overlay with SSH keys and secrets |
| `make generate-inventory` | Regenerate inventory/hosts.yml from proxmox_guests in the platform host vars source |
| `make validate-generated-inventory` | Exit 1 if inventory/hosts.yml is out of sync with proxmox_guests |
| `make bootstrap` | Full platform bootstrap from bare Debian 13 (ADR 0386) |
| `make bootstrap-minimal` | Bootstrap critical path only (PG + Keycloak + Nginx + OpenBao) |
| `make docker-dev-up` | Start minimal Docker dev environment (Tier 1) |
| `make docker-dev-converge` | Run Ansible convergence against Docker dev containers |
| `make converge-<service>` | Deploy a specific service |
| `make verify-platform` | Verify critical platform services are healthy |
| `make validate` | Run full validation suite (YAML, syntax, lint, cross-catalog, types) |
| `make validate-types` | Pyright type-check + bandit SAST on Python scripts and Ansible plugins |
| `make validate-cross-catalog` | Cross-catalog referential integrity check |
| `make generate-readme` | Regenerate README.md from docs/templates/README.md.j2 |
| `make validate-generated-readme` | Exit 1 if README.md is out of sync with template |
| `make publish-serverclaw` | Dry-run: sanitize repo and check for leaks (no push) |

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

---

*Generated 2026-04-12 by [scripts/generate_readme.py](scripts/generate_readme.py)
from [docs/templates/README.md.j2](docs/templates/README.md.j2).
Run `make generate-readme` to refresh.*
