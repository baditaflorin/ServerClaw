# ADR 0386: Reproducible Zero-to-Platform Bootstrap for Public Forks

**Status:** Proposed
**Date:** 2026-04-09
**Concern:** Bootstrap, Fork Portability, Public Release Readiness

---

## Context

The platform has mature automation — 73 declared services, full Ansible
convergence, ADR governance, onboarding packs, and a reference deployment
system (ADR 0339). But when a new user clones the repo onto a fresh machine,
there is **no single documented path** from "I have a server and this repo"
to "platform is fully operational."

Today's bootstrap knowledge lives in five separate places:

| Location | What it covers | What it lacks |
|----------|---------------|---------------|
| `docs/runbooks/initial-access.md` | Hetzner Rescue + installimage | Non-Hetzner providers; post-OS steps |
| `Makefile` targets (`install-proxmox`, `provision-guests`, …) | Individual stage commands | Ordering, prerequisites, success criteria |
| `config/controller-local-secrets.json` | Secret manifest (50+ entries) | How to generate each secret from scratch |
| `build/onboarding/fork-bootstrap.yaml` | File discovery for agents | Not actionable by a human operator |
| `.local/` directory (49 subdirs) | Runtime secrets and state | No template, no generator, no documentation of required vs optional |

A fork operator today must: (1) read multiple runbooks and ADRs, (2) reverse-
engineer the `.local/` structure from `controller-local-secrets.json`, (3) guess
the correct `make` target ordering, (4) manually create SSH keys, OpenBao tokens,
database passwords, and OIDC client secrets, and (5) debug failures caused by
missing secrets with no clear error messages.

**The goal:** the repo itself — when cloned onto any target machine — is the
single entrypoint for bootstrapping that machine to a fully operational state.

### What Already Works

Credit where due — the platform has strong foundations for this:

- **ADR 0001 + 0003:** Two-stage bootstrap model (out-of-band OS install,
  then in-band Ansible IaC) is sound and provider-agnostic in principle
- **ADR 0339:** Reference deployment system with provider profiles
- **ADR 0373:** `derive_service_defaults` eliminates per-role boilerplate
- **ADR 0385:** `platform_topology_host` indirection removes hostname coupling
- **`playbooks/proxmox-install.yml`:** Full Proxmox installation sequence
  (13 roles, Debian 13 validated)
- **`playbooks/site.yml`:** Full host convergence entrypoint
- **Preflight role:** Validates prerequisites before convergence

### What Is Missing

1. **`.local-example/` scaffold** — No template showing the required directory
   structure, file formats, and which secrets are required vs optional vs
   auto-generated
2. **`make bootstrap` single entrypoint** — No command that runs the full
   sequence (init-local → install-proxmox → provision-guests → converge-site)
   with prerequisite checks between stages
3. **Secret generation tooling** — No `make init-secrets` that generates
   random passwords, SSH keypairs, self-signed bootstrap certs, and stub
   config files from the manifest
4. **Provider abstraction layer** — The bootstrap runbook assumes Hetzner
   Rescue + installimage; other providers (OVH, bare-metal colo, local lab)
   need equivalent guidance
5. **Bootstrap validation** — No `make verify-bootstrap` that checks the
   host reached the expected post-install state before proceeding to
   guest provisioning
6. **Dependency graph documentation** — The Makefile has ~200 targets with
   implicit ordering; no machine-readable or human-readable dependency graph
   exists for the bootstrap sequence

---

## Decision

Implement a **four-layer bootstrap system** that takes a fork operator from
"I have a server with Debian 13 and SSH access" to "platform fully converged"
through a single documented path.

### Layer 1: Local Overlay Scaffold (`make init-local`)

Create a `.local-example/` directory in the repo containing:

```
.local-example/
├── README.md                          # What this directory is, how to use it
├── ssh/
│   └── .gitkeep                       # Operator generates bootstrap.id_ed25519 here
├── openbao/
│   ├── init-keys.json.example         # Structure template with placeholder values
│   └── .gitkeep
├── keycloak/
│   ├── admin-password.txt.example     # "CHANGE_ME" placeholder
│   └── .gitkeep
├── monitoring/
│   └── .gitkeep
└── [per-service directories]/
    └── .gitkeep
```

Add a `make init-local` target that:

1. Copies `.local-example/` to `.local/` (abort if `.local/` already exists)
2. Generates an ED25519 SSH keypair at `.local/ssh/bootstrap.id_ed25519`
3. Generates random passwords for all `generated_by_repo` secrets listed in
   `config/controller-local-secrets.json`
4. Creates stub `.env` files for services that need them
5. Prints a checklist of secrets that must be provided externally
   (API keys, domain registrar tokens, etc.)

Implementation: `scripts/init_local_overlay.py` reading from
`config/controller-local-secrets.json` as the authoritative manifest.

### Layer 2: Provider Bootstrap Profiles

Extend the reference deployment system (ADR 0339) with **provider bootstrap
profiles** that document the out-of-band steps per hosting provider:

```yaml
# config/provider-profiles/hetzner-dedicated.yaml
provider: hetzner-dedicated
bootstrap_method: rescue-installimage
prerequisites:
  - Hetzner Robot account with server access
  - Server in rescue mode (Linux 64-bit)
steps:
  - name: Install Debian 13 via installimage
    manual: true
    runbook: docs/runbooks/initial-access.md
    validation: ssh root@<server-ip> "cat /etc/debian_version"
  - name: Run Ansible bootstrap
    command: make bootstrap-host HOST=<server-ip>
    validation: make verify-bootstrap HOST=<server-ip>

# config/provider-profiles/generic-debian.yaml
provider: generic-debian
bootstrap_method: existing-debian-13
prerequisites:
  - Debian 13 server with root SSH access
  - At least 32 GB RAM, 500 GB disk
steps:
  - name: Verify Debian 13
    command: ssh root@<server-ip> "cat /etc/debian_version"
  - name: Run Ansible bootstrap
    command: make bootstrap-host HOST=<server-ip>
    validation: make verify-bootstrap HOST=<server-ip>
```

### Layer 3: Staged Bootstrap Entrypoint (`make bootstrap`)

Add a top-level `make bootstrap` target that orchestrates the full sequence
with validation gates between stages:

```makefile
bootstrap: ## Full platform bootstrap from bare Debian 13
	@echo "=== Stage 1: Local overlay initialization ==="
	$(MAKE) init-local
	@echo ""
	@echo "=== Stage 2: Proxmox VE installation ==="
	$(MAKE) install-proxmox
	$(MAKE) verify-bootstrap-proxmox
	@echo ""
	@echo "=== Stage 3: Network and access ==="
	$(MAKE) configure-network
	$(MAKE) configure-tailscale
	$(MAKE) harden-access
	@echo ""
	@echo "=== Stage 4: Guest provisioning ==="
	$(MAKE) provision-guests
	$(MAKE) verify-bootstrap-guests
	@echo ""
	@echo "=== Stage 5: Platform convergence ==="
	$(MAKE) converge-site
	$(MAKE) verify-platform
	@echo ""
	@echo "=== Bootstrap complete ==="
```

Each `verify-bootstrap-*` target runs lightweight Ansible playbooks that
assert expected state:

- `verify-bootstrap-proxmox`: PVE packages installed, API accessible,
  storage pools exist, networking configured
- `verify-bootstrap-guests`: All declared VMs exist, are running, respond
  to SSH on expected IPs
- `verify-platform`: Critical services healthy (Keycloak, PostgreSQL,
  Nginx, OpenBao), DNS resolving, TLS valid

### Layer 4: Bootstrap Runbook for Humans

Create `docs/runbooks/bootstrap-from-scratch.md` — a single document that
a human operator reads end-to-end. Structure:

```
1. Prerequisites (hardware, accounts, domain)
2. Clone the repo
3. Run `make init-local` and fill in external secrets
4. Choose your provider profile
5. Run `make bootstrap` (or step-by-step if preferred)
6. Verify with `make verify-platform`
7. Post-bootstrap: set up DNS, TLS certificates, SSO
8. Troubleshooting common failures
```

This runbook replaces the need to read 5+ separate documents.

### Inventory Template for Forks

Create `inventory/hosts.yml.example` showing the structure a fork must fill in:

```yaml
all:
  children:
    proxmox_hosts:
      hosts:
        your-proxmox-host:          # Replace with your hostname
          ansible_host: <SERVER_IP>  # Replace with your server's IP
          ansible_user: root
    lv3_guests:
      hosts:
        your-docker-runtime:
          ansible_host: 10.10.10.20  # Internal VM IP (customizable)
          # ... guest definitions
```

The `make init-local` step includes guidance on copying this to `hosts.yml`
and customizing it.

---

## Consequences

### Positive

- **Single-path bootstrap:** Any operator can go from bare server to
  running platform following one runbook
- **Fork-friendly:** `.local-example/` and `hosts.yml.example` eliminate
  the reverse-engineering step for new forks
- **Provider-agnostic:** Provider profiles decouple the out-of-band OS
  install from the in-band IaC, making non-Hetzner deployments first-class
- **Validation gates:** `verify-bootstrap-*` targets catch misconfigurations
  early instead of failing deep into convergence
- **Secret generation:** `init-local` eliminates the most common fork
  failure mode (missing or malformed `.local/` files)

### Negative

- **Maintenance burden:** `.local-example/` must be kept in sync with
  `controller-local-secrets.json` — add a CI check for drift
- **Provider profiles are documentation, not automation:** The out-of-band
  OS install step remains manual for most providers
- **Bootstrap is still slow:** Full convergence of 73 services takes
  significant time; no shortcut for "minimal viable platform"

### Mitigation

- Add a `make bootstrap-minimal` target that converges only the critical
  path (Proxmox → Docker runtime → PostgreSQL → Keycloak → Nginx) — enough
  to prove the platform works, with remaining services added incrementally
- Add a pre-commit hook that validates `.local-example/` against the
  secret manifest
- Document expected wall-clock time for each bootstrap stage

---

## Implementation Phases

### Phase 1: Foundation (1-2 weeks)

- [ ] Create `.local-example/` scaffold from `controller-local-secrets.json`
- [ ] Write `scripts/init_local_overlay.py`
- [ ] Add `make init-local` target
- [ ] Create `inventory/hosts.yml.example`
- [ ] Write `docs/runbooks/bootstrap-from-scratch.md`

### Phase 2: Validation (1 week)

- [ ] Create `verify-bootstrap-proxmox` playbook
- [ ] Create `verify-bootstrap-guests` playbook
- [ ] Create `verify-platform` playbook
- [ ] Add `make bootstrap` orchestration target
- [ ] Add `make bootstrap-minimal` for fast iteration

### Phase 3: Provider Profiles (1 week)

- [ ] Create `config/provider-profiles/` directory
- [ ] Write Hetzner dedicated profile
- [ ] Write generic Debian 13 profile
- [ ] Write local-lab / homelab profile (for development)
- [ ] Document "bring your own provider" extension pattern

### Phase 4: Polish (ongoing)

- [ ] CI check: `.local-example/` ↔ `controller-local-secrets.json` drift
- [ ] Pre-commit hook for inventory example freshness
- [ ] Onboarding pack generation includes bootstrap steps
- [ ] Test full bootstrap on a fresh Hetzner server (end-to-end validation)

---

## Related ADRs

- **ADR 0001:** Bootstrap Dedicated Host With Ansible (foundation)
- **ADR 0003:** Prefer Hetzner Rescue + installimage (current provider path)
- **ADR 0220:** Bootstrap and recovery sequencing for environment cells
- **ADR 0268:** Fresh worktree bootstrap manifests
- **ADR 0339:** Reference deployment system with provider profiles
- **ADR 0373:** derive_service_defaults (reduces per-fork config burden)
- **ADR 0385:** Decouple platform from operator identity (prerequisite for forks)
- **ADR 0387:** ServerClaw-in-Docker (companion — containerized alternative to bare metal)
