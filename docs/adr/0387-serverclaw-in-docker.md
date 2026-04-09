# ADR 0387: ServerClaw-in-Docker — Containerized Platform Development Environment

**Status:** Proposed
**Date:** 2026-04-09
**Concern:** Developer Experience, Fork Portability, Public Release Readiness

---

## Context

The ServerClaw platform currently requires:

- A dedicated Hetzner bare-metal server (or equivalent x86_64 hardware)
- Proxmox VE installed on Debian 13
- 17 VMs provisioned with specific IP addresses
- 73 services deployed across those VMs

This makes it impossible for a potential user to:

1. **Try the platform** without committing to expensive bare-metal hardware
2. **Develop locally** on an ARM MacBook (the primary development machine)
3. **Run CI/CD tests** that validate the full platform topology
4. **Onboard new contributors** who don't have access to the production Hetzner server

The vision: **any developer should be able to `docker compose up` and get a
working ServerClaw platform on their laptop** — even if at reduced scale.

### Constraints

| Constraint | Impact |
|------------|--------|
| Primary dev machine is ARM (Apple Silicon M-series) | Cannot run Proxmox VE natively (x86_64 only); QEMU emulation is slow |
| Proxmox VE requires bare-metal or nested virtualization | Cannot run inside a standard Docker container |
| 73 services need ~32GB RAM in production | Laptop cannot run all services simultaneously |
| Ansible expects SSH access to VMs at specific IPs | Docker containers need to appear as SSH-accessible hosts on a predictable network |
| Some services require GPU (Ollama, inference workloads) | Must gracefully degrade without GPU |

### Prior Art

| Project | Approach | Limitation |
|---------|----------|------------|
| k3d / kind | Kubernetes-in-Docker | Wrong orchestrator (this platform is Ansible + Docker Compose, not K8s) |
| Vagrant | VMs via VirtualBox/libvirt | Heavy, poor ARM Mac support since VirtualBox dropped ARM |
| Lima | Linux VMs on macOS | Good for single VM, awkward for multi-VM topology |
| Colima | Docker runtime on macOS | Runs Docker but not multi-VM Proxmox topology |
| Proxmox in QEMU | Full Proxmox in emulated x86 | Very slow on ARM; 16+ GB RAM overhead for the hypervisor alone |

---

## Decision

Implement a **three-tier containerized development environment** that
progressively approximates production fidelity without requiring bare metal.

### Architecture: Containers as VM Stand-ins

Instead of running actual Proxmox VE, **replace each VM with a Docker
container** that exposes the same interface Ansible expects: SSH access,
a predictable IP, and the ability to run Docker Compose inside it
(Docker-in-Docker).

```
┌─────────────────────────────────────────────────────────────┐
│                     Host Machine (macOS/Linux)               │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Docker Network: serverclaw              │    │
│  │              Subnet: 10.10.10.0/24                   │    │
│  │                                                      │    │
│  │  ┌──────────────┐  ┌──────────────┐                 │    │
│  │  │ control-plane │  │  postgres-vm  │                │    │
│  │  │ 10.10.10.20   │  │ 10.10.10.60  │                │    │
│  │  │ SSH + DinD    │  │ SSH + PG 16  │                │    │
│  │  └──────────────┘  └──────────────┘                 │    │
│  │                                                      │    │
│  │  ┌──────────────┐  ┌──────────────┐                 │    │
│  │  │  nginx-edge   │  │  backup-vm   │                │    │
│  │  │ 10.10.10.10   │  │ 10.10.10.40  │                │    │
│  │  │ SSH + Nginx   │  │ SSH + PBS    │                │    │
│  │  └──────────────┘  └──────────────┘                 │    │
│  │                                                      │    │
│  │  ┌──────────────┐  ┌──────────────┐                 │    │
│  │  │ monitoring-vm │  │  build-srv   │                │    │
│  │  │ 10.10.10.50   │  │ 10.10.10.30  │                │    │
│  │  │ SSH + Grafana │  │ SSH + DinD   │                │    │
│  │  └──────────────┘  └──────────────┘                 │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Ansible Controller (host)                │    │
│  │  inventory/hosts-docker.yml → same IPs as above      │    │
│  │  ansible-playbook -i inventory/hosts-docker.yml ...  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Tier 1: Minimal Viable Platform (`docker-dev/minimal/`)

Run only the critical-path services needed to prove the platform works:

**Containers:** 4
- `postgres-vm` — PostgreSQL 16 with all required databases
- `control-plane` — Docker runtime hosting Keycloak, OpenBao, Nginx
- `nginx-edge` — Public edge proxy
- `monitoring-vm` — Grafana + Prometheus (optional, can be disabled)

**Resource requirements:** 8 GB RAM, 4 CPU cores, 20 GB disk

**What works at this tier:**
- SSO login via Keycloak
- Secret management via OpenBao
- Database access via shared PostgreSQL
- Reverse proxy via Nginx
- Ansible convergence of the above services

**What doesn't work:**
- Services beyond the critical path (Dify, Nextcloud, etc.)
- Backup and recovery (no PBS)
- Build server (Docker builds happen on host)

### Tier 2: Full Topology (`docker-dev/full/`)

Run all 6-7 VM-equivalent containers with the complete service catalog:

**Containers:** 7 (matching production VM topology)
- All Tier 1 containers plus:
- `build-srv` — Build server with Docker-in-Docker
- `backup-vm` — Backup target
- `coolify-vm` — Coolify runtime (optional)

**Resource requirements:** 16-24 GB RAM, 8 CPU cores, 50 GB disk

**What works at this tier:**
- All 73 services (resource permitting)
- Full Ansible convergence with `site.yml`
- Inter-service communication on production-equivalent IPs
- Backup and recovery workflows

### Tier 3: Proxmox-Equivalent (`docker-dev/proxmox/`)

For users who want to test Proxmox-specific automation (VM provisioning,
storage pools, host control loops), provide a **QEMU-in-Docker** setup
that runs an actual Proxmox VE instance:

**Containers:** 1 (QEMU/KVM host) + nested VMs inside
- Uses `qemux/qemu-docker` or equivalent QEMU-in-Docker image
- Runs actual Proxmox VE ISO installer inside QEMU
- Requires x86_64 host (Linux with KVM, or GitHub Codespaces)
- **Not supported on ARM Macs** (too slow via emulation)

**Resource requirements:** 32 GB RAM, 8+ CPU cores, 100 GB disk, KVM support

**What works at this tier:**
- Full `make install-proxmox` workflow
- VM provisioning via Proxmox API
- Storage pool configuration
- Host control loops (ADR 0226)
- Complete end-to-end bootstrap validation

### The VM-as-Container Base Image

Build a `serverclaw/vm-base` Docker image that simulates what Ansible expects
from a freshly provisioned Ubuntu VM:

```dockerfile
# docker-dev/images/vm-base/Dockerfile
FROM ubuntu:24.04

# SSH server (Ansible's transport)
RUN apt-get update && apt-get install -y \
    openssh-server sudo python3 python3-apt \
    systemctl docker.io ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Create ops user (matches production access model)
RUN useradd -m -s /bin/bash -G sudo,docker ops \
    && echo "ops ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/ops

# SSH key injection (bootstrap key from .local/)
RUN mkdir -p /home/ops/.ssh && chmod 700 /home/ops/.ssh
# Key is bind-mounted at runtime from .local/ssh/

# Docker-in-Docker support
VOLUME /var/lib/docker

# Systemd init (some roles expect systemd)
ENTRYPOINT ["/sbin/init"]
```

### Docker Compose Orchestration

```yaml
# docker-dev/minimal/docker-compose.yml
version: "3.8"

networks:
  serverclaw:
    driver: bridge
    ipam:
      config:
        - subnet: 10.10.10.0/24

services:
  postgres-vm:
    build: ../images/vm-base
    hostname: postgres-vm
    privileged: true        # for systemd + DinD
    networks:
      serverclaw:
        ipv4_address: 10.10.10.60
    volumes:
      - ../../.local/ssh/bootstrap.id_ed25519.pub:/home/ops/.ssh/authorized_keys:ro
      - postgres-data:/var/lib/postgresql
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "postgres"]
      interval: 10s

  control-plane:
    build: ../images/vm-base
    hostname: docker-runtime
    privileged: true
    networks:
      serverclaw:
        ipv4_address: 10.10.10.20
    volumes:
      - ../../.local/ssh/bootstrap.id_ed25519.pub:/home/ops/.ssh/authorized_keys:ro
      - /var/run/docker.sock:/var/run/docker.sock  # DinD
    depends_on:
      postgres-vm:
        condition: service_healthy

  nginx-edge:
    build: ../images/vm-base
    hostname: nginx-edge
    privileged: true
    networks:
      serverclaw:
        ipv4_address: 10.10.10.10
    ports:
      - "8443:443"     # HTTPS on host port 8443
      - "8080:80"      # HTTP on host port 8080
    volumes:
      - ../../.local/ssh/bootstrap.id_ed25519.pub:/home/ops/.ssh/authorized_keys:ro

volumes:
  postgres-data:
```

### Inventory Overlay for Docker Development

```yaml
# inventory/hosts-docker.yml
all:
  vars:
    ansible_user: ops
    ansible_ssh_private_key_file: "{{ playbook_dir }}/../.local/ssh/bootstrap.id_ed25519"
    ansible_python_interpreter: /usr/bin/python3
    # Override: no Proxmox API in Docker mode
    platform_environment: docker-dev
    platform_skip_proxmox_api: true
  children:
    proxmox_hosts:
      hosts:
        localhost:
          ansible_connection: local
          # Stub: Proxmox API calls are skipped in docker-dev mode
    lv3_guests:
      hosts:
        docker-runtime:
          ansible_host: 10.10.10.20
        postgres-vm:
          ansible_host: 10.10.10.60
        nginx-edge:
          ansible_host: 10.10.10.10
```

### Makefile Integration

```makefile
# --- Docker Development Environment ---

docker-dev-up:          ## Start minimal Docker dev environment
	docker compose -f docker-dev/minimal/docker-compose.yml up -d
	@echo "Waiting for containers to be ready..."
	@sleep 5
	$(MAKE) docker-dev-verify

docker-dev-up-full:     ## Start full-topology Docker dev environment
	docker compose -f docker-dev/full/docker-compose.yml up -d

docker-dev-down:        ## Stop Docker dev environment
	docker compose -f docker-dev/minimal/docker-compose.yml down
	docker compose -f docker-dev/full/docker-compose.yml down 2>/dev/null || true

docker-dev-converge:    ## Run site.yml against Docker dev environment
	$(ANSIBLE_PLAYBOOK_CMD) -i inventory/hosts-docker.yml playbooks/site.yml

docker-dev-verify:      ## Verify Docker dev environment health
	@echo "Checking SSH access to containers..."
	@for host in 10.10.10.20 10.10.10.60 10.10.10.10; do \
	  ssh -o StrictHostKeyChecking=no -i .local/ssh/bootstrap.id_ed25519 \
	    ops@$$host "echo OK" && echo "  ✓ $$host" || echo "  ✗ $$host"; \
	done

docker-dev-reset:       ## Destroy and recreate Docker dev environment
	$(MAKE) docker-dev-down
	docker volume prune -f
	$(MAKE) docker-dev-up
```

### ARM Mac Compatibility

The `vm-base` image uses `ubuntu:24.04` which has native ARM builds.
Services that require x86 images (rare in this platform) use Docker's
built-in QEMU emulation (`--platform linux/amd64`). The Docker development
environment is designed for:

| Host Architecture | Tier 1 (Minimal) | Tier 2 (Full) | Tier 3 (Proxmox) |
|-------------------|:-:|:-:|:-:|
| ARM Mac (M-series) | ✓ native | ✓ native | ✗ too slow |
| x86_64 Linux (KVM) | ✓ native | ✓ native | ✓ full support |
| x86_64 Mac (Intel) | ✓ native | ✓ native | ✓ with Docker Desktop |
| GitHub Codespaces | ✓ native | ✓ with 16GB | ✓ with 32GB |
| WSL2 on Windows | ✓ native | ✓ native | ✓ with Hyper-V KVM |

### Role Compatibility Layer

Some Ansible roles assume behaviors that differ between real VMs and
containers. Add a `platform_environment` variable that roles can check:

```yaml
# In derive_service_defaults or common role:
# When platform_environment == "docker-dev":
#   - Skip ufw/firewall rules (no iptables in unprivileged containers)
#   - Skip systemd timer creation (use crond instead)
#   - Skip Proxmox API calls (no hypervisor)
#   - Skip Tailscale/Headscale (no VPN in Docker network)
#   - Use Docker network DNS instead of CoreDNS/split-horizon
```

This is a thin compatibility shim, not a parallel implementation.
The goal is 95% of roles working unmodified, with 5% having a
`when: platform_environment != 'docker-dev'` guard on
infrastructure-specific tasks.

---

## Consequences

### Positive

- **Zero-cost trial:** Anyone can experience the platform with just Docker
  installed — no server, no money, no commitment
- **Fast development loop:** Change a role, `make docker-dev-converge`,
  see result in seconds instead of waiting for SSH to a remote server
- **CI/CD validation:** GitHub Actions can spin up Tier 1 to validate PRs
  against a real multi-host topology
- **Contributor onboarding:** New contributors can explore and modify the
  platform locally before touching production
- **ARM Mac native:** Tier 1 and 2 work natively on Apple Silicon without
  x86 emulation overhead
- **Reproducible demos:** `docker compose up` is the ultimate "it works
  on my machine" proof

### Negative

- **Fidelity gap:** Containers are not VMs — no real kernel isolation,
  no Proxmox API, no true systemd, no real network stack
- **DinD complexity:** Docker-in-Docker is fragile; some services may
  behave differently with nested Docker
- **Maintenance surface:** `vm-base` image and Docker Compose files must
  track changes to the production VM baseline
- **Resource hunger:** Even Tier 1 needs 8 GB RAM — not trivial on a
  laptop running other workloads
- **Proxmox gap:** Tier 3 requires x86 + KVM, which excludes the primary
  dev machine (ARM Mac)

### Mitigation

- **Fidelity gap:** Document known differences in
  `docker-dev/KNOWN-DIFFERENCES.md`; accept that Docker-dev is for
  development velocity, not production fidelity testing
- **DinD fragility:** Use Docker socket bind-mount where possible instead
  of true DinD; fall back to DinD only for the build server container
- **Maintenance:** Generate `docker-compose.yml` from the same
  `inventory/hosts.yml` and `platform_service_registry` that drives
  production — reduces drift
- **ARM Proxmox gap:** Tier 3 targets CI (GitHub Actions x86 runners)
  and Linux workstations, not developer laptops; document this clearly

---

## Implementation Phases

### Phase 1: VM-Base Image + Minimal Tier (2-3 weeks)

- [ ] Create `docker-dev/images/vm-base/Dockerfile`
- [ ] Create `docker-dev/minimal/docker-compose.yml` with 3-4 containers
- [ ] Create `inventory/hosts-docker.yml`
- [ ] Add `platform_environment` variable and guards in `common` role
- [ ] Add `make docker-dev-up`, `make docker-dev-down`, `make docker-dev-converge`
- [ ] Validate: Keycloak + PostgreSQL + Nginx converge successfully
- [ ] Write `docker-dev/README.md` with quickstart

### Phase 2: Full Topology + CI Integration (2-3 weeks)

- [ ] Create `docker-dev/full/docker-compose.yml` with all VM containers
- [ ] Add health checks and dependency ordering
- [ ] Create GitHub Actions workflow that runs `make docker-dev-converge`
- [ ] Audit all roles for Docker-dev compatibility; add guards where needed
- [ ] Create `docker-dev/KNOWN-DIFFERENCES.md`

### Phase 3: Proxmox Tier + End-to-End Testing (3-4 weeks)

- [ ] Evaluate QEMU-in-Docker options (`qemux/qemu-docker`, custom build)
- [ ] Create `docker-dev/proxmox/docker-compose.yml` with QEMU container
- [ ] Automate Proxmox VE installation inside QEMU
- [ ] Validate `make install-proxmox` + `make provision-guests` inside container
- [ ] Add to CI as a nightly (not per-PR) validation

### Phase 4: Compose Generation from Inventory (future)

- [ ] Write `scripts/generate_docker_dev_compose.py` that reads
  `inventory/hosts.yml` and `platform_service_registry` to auto-generate
  Docker Compose files — eliminating manual drift between production
  inventory and Docker dev environment

---

## Related ADRs

- **ADR 0001:** Bootstrap Dedicated Host With Ansible (production path)
- **ADR 0003:** Prefer Hetzner Rescue + installimage (provider-specific)
- **ADR 0339:** Reference deployment system (provider profiles)
- **ADR 0347:** Docker runtime workload split (VM topology decisions)
- **ADR 0373:** derive_service_defaults (reduces per-environment config)
- **ADR 0385:** Decouple platform from operator identity (fork portability)
- **ADR 0386:** Reproducible zero-to-platform bootstrap (companion — bare metal path)
