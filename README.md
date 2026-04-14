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

## Platform Status

<!-- BEGIN GENERATED: platform-status -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

### Current Values
| Field | Value |
| --- | --- |
| Repository version | `0.178.137` |
| Platform version | `0.178.133` |
| Observed check date | `2026-04-03` |
| Observed OS | `Debian 13` |
| Observed Proxmox version | `9.1.6` |
| Observed kernel | `6.17.13-2-pve` |

### Topology Summary
| Field | Value |
| --- | --- |
| Managed guest count | 17 |
| Running guest count | 10 |
| Template VM present | `true` |
| Declared services | 71 |
| Publicly published services | 47 |

### Service Exposure Summary
| Exposure Model | Services |
| --- | --- |
| `edge-published` | 38 |
| `edge-static` | 1 |
| `informational-only` | 4 |
| `private-only` | 28 |

### Latest Live-Apply Evidence
| Capability | Receipt |
| --- | --- |
| `postgres_vm` | `2026-04-13-adr-0359-declarative-postgresql-client-registry-live-apply` |
| `woodpecker` | `2026-04-12-ws-0025-compose-stack-lifecycle-mainline-live-apply` |
| `neko` | `2026-04-12-adr-0380-neko-exact-main-live-apply` |
| `mail_platform` | `2026-04-12-ws-0025-compose-stack-lifecycle-mainline-live-apply` |
| `litellm` | `2026-04-12-adr-0374-cross-cutting-service-manifest-live-apply` |
| `librechat` | `2026-04-12-adr-0374-cross-cutting-service-manifest-live-apply` |
| `docker_runtime` | `2026-04-12-ws-0025-compose-stack-lifecycle-mainline-live-apply` |
| `vikunja` | `2026-04-10-adr-0388-keycloak-oidc-9-services-live-apply` |
| `identity_core_watchdog` | `2026-04-10-adr-0388-keycloak-oidc-9-services-live-apply` |
| `headscale` | `2026-04-10-adr-0388-keycloak-oidc-9-services-live-apply` |
| `platform` | `2026-04-09-adr-0373-phases5-6-100pct-adoption-live-apply` |
| `ollama` | `2026-04-07-ollama-serverclaw-gemma4-live-apply` |
| `windmill` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `vaultwarden` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `uptime_kuma` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `temporal` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `step_ca` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `semaphore` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `openfga` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `openbao` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |

Showing 20 of 178 capability receipts. Full history: [live-apply evidence history](docs/status/history/live-apply-evidence.md)
<!-- END GENERATED: platform-status -->

## Version Summary

<!-- BEGIN GENERATED: version-summary -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

| Field | Value |
| --- | --- |
| Repository version | `0.178.137` |
| Platform version | `0.178.133` |
| Observed OS | `Debian 13` |
| Observed Proxmox installed | `true` |
| Observed PVE manager version | `9.1.6` |
| Declared services | 71 |
<!-- END GENERATED: version-summary -->

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
make generate-inventory      # Generate inventory/hosts.yml from platform-host.yml
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
- **270+ runbooks** — Step-by-step procedures an AI agent can follow
- **Workstream tracking** — Parallel agent sessions coordinate via YAML manifests

Point Claude Code at this repo and it knows how to deploy, debug, and extend
every service.

## Control Plane Lanes

<!-- BEGIN GENERATED: control-plane-lanes -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

### Lane Summary
| Lane | Title | Transport | Surfaces | Primary Rule |
| --- | --- | --- | --- | --- |
| `command` | Command Lane | `ssh` | 2 | Use SSH only for command-lane access. |
| `api` | API Lane | `https` | 14 | Default new APIs to internal-only or operator-only publication. |
| `message` | Message Lane | `authenticated_submission` | 2 | Submit platform mail through the internal mail platform rather than arbitrary external SMTP relays. |
| `event` | Event Lane | `mixed` | 16 | Event sinks must be documented and intentionally reachable. |

### API Publication Tiers
| Tier | Title | Surfaces | Summary |
| --- | --- | --- | --- |
| `internal-only` | Internal-Only | 20 | Reachable only from LV3 private networks, loopback paths, or explicitly trusted control-plane hosts. |
| `operator-only` | Operator-Only | 7 | Reachable only from approved operator devices over private access such as Tailscale. |
| `public-edge` | Public Edge | 3 | Intentionally published on a public domain through the named edge model. |
<!-- END GENERATED: control-plane-lanes -->

## What This Is

A single Git repository that contains everything needed to operate a
self-hosted platform:

| Layer | What | Count |
|-------|------|-------|
| Architecture decisions | `docs/adr/` | 443+ ADRs |
| Ansible roles | `collections/ansible_collections/lv3/platform/roles/` | 160 roles |
| Playbooks | `collections/ansible_collections/lv3/platform/playbooks/` | 61 playbooks |
| Operational runbooks | `docs/runbooks/` | 270+ runbooks |
| Automation scripts | `scripts/` | 309+ scripts |
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
2. Run `make generate-inventory` — generates `inventory/hosts.yml` from `inventory/host_vars/platform-host.yml`
3. Run `make init-local` to generate secrets
4. Choose a [provider profile](config/provider-profiles/) (cloud, generic Debian, homelab)
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
  +-- runtime-control   (10.0.0.92)  API gateway, agent tools
  +-- runtime-ai        (10.0.0.90)  GPU workloads (Ollama, inference)
  +-- [additional VMs per topology]
```

All guest VMs are managed declaratively. `inventory/host_vars/platform-host.yml`
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
  `proxmox_guests` in `platform-host.yml`. Edit the source, not the output.
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
│   ├── runbooks/        # 270+ operational runbooks
│   └── templates/       # Jinja2 templates for generated docs (incl. this README)
├── scripts/             # 309+ automation scripts
├── local-overlay-template/  # Scaffold for .local/ secrets directory
└── Makefile             # 27+ automation targets
```

Full layout: [.repo-structure.yaml](.repo-structure.yaml)

## Make Targets

<!-- Generated from Makefile '## ' annotations by scripts/generate_readme.py -->
| Target | Description |
|--------|-------------|
| `make init-local` | Initialize .local/ overlay with SSH keys and secrets |
| `make generate-inventory` | Regenerate inventory/hosts.yml from proxmox_guests in host_vars/platform-host.yml |
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

## Document Index

<!-- BEGIN GENERATED: document-index -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

### Core Documents
- [Changelog](changelog.md)
- [Release notes](docs/release-notes/README.md)
- [Repository map](docs/repository-map.md)
- [Assistant operator guide](docs/assistant-operator-guide.md)
- [Release process](docs/release-process.md)
- [Workstreams registry](workstreams.yaml)
- [Workstreams guide](docs/workstreams/README.md)

### Discovery Indexes
- [ADR index](docs/adr/.index.yaml)
- [Runbooks directory](docs/runbooks)
- [Workstreams directory](docs/workstreams)
- [Release notes index](docs/release-notes/README.md)
- [Generated docs directory](docs/site-generated)
<!-- END GENERATED: document-index -->

## Recently Merged Workstreams

<!-- BEGIN GENERATED: merged-workstreams -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

Showing 25 of 308 merged or live-applied workstreams. Full history: [merged workstream history](docs/status/history/merged-workstreams.md)

| ADR | Title | Status | Doc |
| --- | --- | --- | --- |
| `0374` | Repair ADR 0374 status artifacts on latest origin/main | `merged` | [ws-0374-status-repair.md](docs/workstreams/ws-0374-status-repair.md) |
| `0368` | DRY Centralization — ADRs 0368–0374 | `merged` | [0368-docker-compose-jinja2-macro-library.md](docs/adr/0368-docker-compose-jinja2-macro-library.md) |
| `0364` | Outline agent tools: list/search/get/create documents (ADR 0362 + 0364) | `merged` | [0362-agent-service-api-gateway-pattern.md](docs/adr/0362-agent-service-api-gateway-pattern.md) |
| `0336` | Verify ADR 0336 public entrypoint leakage validation on the latest origin/main | `merged` | [ws-0336-live-apply.md](docs/workstreams/ws-0336-live-apply.md) |
| `0309` | Live apply task-oriented information architecture across the platform workbench from latest origin/main | `live_applied` | [ws-0309-live-apply.md](docs/workstreams/ws-0309-live-apply.md) |
| `0297` | Resolve Gitea release bundle retention and Renovate PR validation checkout drift | `live_applied` | [ws-0315-gitea-followups.md](docs/workstreams/ws-0315-gitea-followups.md) |
| `0295` | Live apply the shared artifact cache plane from latest origin/main | `live_applied` | [ws-0295-live-apply.md](docs/workstreams/ws-0295-live-apply.md) |
| `0293` | Integrate ADR 0293 exact-main LiveKit replay onto main | `merged` | [ws-0293-main-integration.md](docs/workstreams/ws-0293-main-integration.md) |
| `0259` | Integrate ADR 0259 exact-main replay onto current origin/main | `merged` | [ws-0259-main-merge.md](docs/workstreams/ws-0259-main-merge.md) |
| `0252` | Integrate ADR 0252 exact-main replay onto current origin/main | `merged` | [ws-0252-main-merge.md](docs/workstreams/ws-0252-main-merge.md) |
| `0238` | Integrate ADR 0238 operator grid into origin/main | `merged` | [ws-0238-main-integration.md](docs/workstreams/ws-0238-main-integration.md) |
| `0237` | Live apply schema-first human forms via React Hook Form and Zod | `live_applied` | [ws-0237-live-apply.md](docs/workstreams/ws-0237-live-apply.md) |
| `0236` | Live apply TanStack Query server-state conventions on the Windmill operator admin app | `live_applied` | [ws-0236-live-apply.md](docs/workstreams/ws-0236-live-apply.md) |
| `0232` | Integrate ADR 0232 live apply into origin/main | `merged` | [ws-0232-main-merge.md](docs/workstreams/ws-0232-main-merge.md) |
| `0206` | Integrate ADR 0206 live apply into origin/main | `merged` | [ws-0206-main-merge.md](docs/workstreams/ws-0206-main-merge.md) |
| `0181` | Off-host witness and control metadata replication | `live_applied` | [adr-0181-off-host-witness-replication.md](docs/workstreams/adr-0181-off-host-witness-replication.md) |
| `0179` | Service redundancy tier matrix | `merged` | [adr-0179-service-redundancy-tier-matrix.md](docs/workstreams/adr-0179-service-redundancy-tier-matrix.md) |
| `0178` | Dependency wave manifests for parallel apply | `merged` | [adr-0178-dependency-wave-manifests.md](docs/workstreams/adr-0178-dependency-wave-manifests.md) |
| `0176` | Inventory sharding and host-scoped Ansible execution | `live_applied` | [adr-0176-inventory-sharding.md](docs/workstreams/adr-0176-inventory-sharding.md) |
| `0173` | Workstream surface ownership manifest | `live_applied` | [adr-0173-workstream-surface-ownership-manifest.md](docs/workstreams/adr-0173-workstream-surface-ownership-manifest.md) |
| `0172` | Watchdog escalation and stale job self-healing | `merged` | [adr-0172-watchdog-escalation-and-stale-job-self-healing.md](docs/workstreams/adr-0172-watchdog-escalation-and-stale-job-self-healing.md) |
| `0171` | Controlled fault injection for resilience validation | `live_applied` | [adr-0171-controlled-fault-injection.md](docs/workstreams/adr-0171-controlled-fault-injection.md) |
| `0170` | Platform-wide timeout hierarchy | `live_applied` | [adr-0170-timeout-hierarchy.md](docs/workstreams/adr-0170-timeout-hierarchy.md) |
| `0169` | Structured log field contract | `live_applied` | [adr-0169-structured-log-field-contract.md](docs/workstreams/adr-0169-structured-log-field-contract.md) |
| `0168` | Ansible role idempotency CI enforcement | `merged` | [adr-0168-idempotency-ci.md](docs/workstreams/adr-0168-idempotency-ci.md) |
<!-- END GENERATED: merged-workstreams -->

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
