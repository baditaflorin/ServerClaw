# ADR 0084: Packer VM Template Pipeline

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.91.0
- Implemented In Platform Version: 0.130.20
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

All VMs on the Proxmox host are currently created by Ansible playbooks that start from a base Debian cloud image, transfer it via `proxmox_kvm`, resize the disk, and run a provisioning playbook. This approach works but has a significant cost:

- **Slow VM provisioning**: cloud-init bootstrapping + full Ansible role run per VM takes 8–20 minutes for a production-class service
- **Inconsistent base state**: each VM starts from a raw cloud image and accumulates OS-level packages (curl, rsyslog, htop, step-cli, etc.) via Ansible on first run; if those packages differ between runs (apt mirror variance, transient failures), the base state diverges silently
- **No immutable baseline**: there is no snapshot of "a known-good base Debian image with our standard hardening applied"; every VM starts from zero
- **Build server CPU is idle**: Packer builds are CPU-intensive (kernel compilation, image compression) and currently run on the laptop when needed at all; the build server is the correct execution target

The platform needs **golden VM templates**: pre-built, tested, and snapshotted base images on the Proxmox host that new VMs clone from. Packer is the standard tool for building these; it supports the Proxmox provider natively.

## Decision

We will maintain a **Packer VM Template Pipeline** defined under `packer/` and executed on the build server.

### Template inventory

| Template name | Base | Purpose |
|---|---|---|
| `lv3-debian-base` | Debian 12 cloud | Every VM — OS hardening, step-cli, rsyslog, fail2ban, unattended-upgrades |
| `lv3-docker-host` | `lv3-debian-base` | Docker VMs — Docker CE, compose plugin, registry cert trust |
| `lv3-postgres-host` | `lv3-debian-base` | PostgreSQL VMs — PostgreSQL 16, pg_stat_statements, barman-cloud |
| `lv3-ops-base` | `lv3-debian-base` | Operator access VMs — step SSH certificates, audit logging, tmux, vim |

Templates are layered: `lv3-docker-host` starts from the published `lv3-debian-base` template (pulled from the Proxmox template store), not from a raw cloud image.

### Directory structure

```
packer/
  templates/
    lv3-debian-base.pkr.hcl
    lv3-docker-host.pkr.hcl
    lv3-postgres-host.pkr.hcl
    lv3-ops-base.pkr.hcl
  scripts/
    base-hardening.sh       # applied during Packer provisioner
    docker-install.sh
    postgres-install.sh
    step-cli-install.sh
  variables/
    common.pkrvars.hcl      # Proxmox API URL, node name, storage pool
    build-server.pkrvars.hcl  # build server specific overrides
    lv3-*.pkrvars.hcl       # template-specific VMIDs, names, and bootstrap inputs
```

### Build execution

Builds run on the build server via the remote execution gateway (ADR 0082):

```bash
make remote-packer-build IMAGE=lv3-debian-base
```

Which translates to:
```bash
# on build-lv3
docker run --rm \
  -v /opt/builds/proxmox-host_server:/workspace \
  -e PROXMOX_API_TOKEN \
  registry.example.com/check-runner/infra:latest \
  /workspace/scripts/build_packer_template.sh lv3-debian-base
```

Packer communicates with the Proxmox API over the Tailscale network. The API token is injected from OpenBao (ADR 0077 secrets model).

### Template versioning

Template IDs on Proxmox follow the format `9000` (base), `9001` (docker-host), `9002` (postgres-host), `9003` (ops-base). Each rebuild creates a new template and retires the previous one after a 7-day grace period. Template metadata (version, build date, Packer SHA) is recorded in `config/vm-template-manifest.json`.

### Integration with VM provisioning

Ansible playbooks that create VMs will be updated to clone from the relevant template instead of uploading a raw cloud image:

```yaml
- name: create service VM
  community.general.proxmox_kvm:
    clone: "lv3-docker-host"          # template name
    newid: "{{ vm_id }}"
    name: "{{ vm_name }}"
    node: pve
    storage: local-lvm
```

The provisioning playbook only needs to apply service-specific roles, not the base OS setup — halving role run time.

### Automated rebuild triggers

A Windmill workflow (`packer-template-rebuild`) triggers on:
- `packer/` directory changes merged to `main`
- Weekly scheduled run (Sunday 02:00) to pick up security patches in the base image
- Manual trigger via `make remote-packer-build IMAGE=<name>`

## Consequences

**Positive**
- New VM provisioning time drops from 15–20 min to 3–5 min (clone + service-specific roles only)
- Base OS state is identical across all VMs of the same type — no more per-VM apt variance
- Packer builds run on the build server, not the laptop; CPU load is invisible to the operator
- Template rebuild history is recorded in `config/vm-template-manifest.json`; rollback is a manifest edit + VM re-clone

**Negative / Trade-offs**
- Packer templates must be kept in sync with base Ansible roles; a role change that affects OS-level packages requires a template rebuild
- Template storage on Proxmox consumes ~10–15 GB per template; four templates ≈ 50 GB; acceptable on a multi-TB pool
- Initial template build takes ~30 minutes per template (Debian install + provisioner); subsequent incremental rebuilds from a layered template take 8–12 minutes

## Alternatives Considered

- **Continue with cloud-init + full Ansible run**: works but stays slow; does not address base-state consistency
- **LXC container templates**: faster than VMs but cannot run Docker nested or serve as general-purpose VM replacements
- **Proxmox manual snapshots**: non-reproducible and not source-controlled; rejected

## Related ADRs

- ADR 0082: Remote build execution gateway (all Packer builds use this)
- ADR 0083: Docker-based check runner (infra image includes Packer binary)
- ADR 0085: OpenTofu VM lifecycle (clones from templates defined here)
- ADR 0089: Build artifact cache (caches Packer plugin downloads and apt layers)

## Implementation Notes

- Repository implementation landed in `0.91.0` with repo-managed Packer templates under [packer/](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/packer), the manifest at [config/vm-template-manifest.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/vm-template-manifest.json), the build-server helper targets in [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/Makefile), and the Windmill helper at [config/windmill/scripts/packer-template-rebuild.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/windmill/scripts/packer-template-rebuild.py).
- Managed guest cloning now consumes the declared template catalog through [inventory/group_vars/all.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/group_vars/all.yml), [inventory/host_vars/proxmox-host.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/host_vars/proxmox-host.yml), and [roles/proxmox_guests/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/collections/ansible_collections/lv3/platform/roles/proxmox_guests/tasks/main.yml).
- Live publication of the four templates and manifest hydration still depends on running the rebuild flow from a credentialed worker against the Proxmox API.
