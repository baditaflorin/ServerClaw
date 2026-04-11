# ADR 0085: OpenTofu IaC for VM Lifecycle Management

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.92.0
- Implemented In Platform Version: 0.39.0
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

VM lifecycle on the Proxmox host is currently managed by a mix of:

1. **Ansible `community.general.proxmox_kvm` tasks** — creation and initial configuration
2. **Manual Proxmox UI operations** — resizing disks, changing CPU/RAM, network adjustments
3. **Ad-hoc shell commands** — node-level operations that don't have an Ansible module
4. **`versions/stack.yaml`** — documents intent but has no enforcement

This creates drift between documented intent and actual Proxmox state. The `stack.yaml` says a VM has 2 vCPUs; the Proxmox UI shows 4 (changed manually during a performance incident, never rolled back). Nobody knows if the Ansible create task would conflict with the actual VM if re-run.

The correct abstraction for **VM lifecycle** (create, resize, destroy, network assignment, snapshot policy) is a declarative IaC tool with a state file, not an Ansible playbook. Ansible is excellent for **configuration inside a VM**; it is a poor fit for **cloud/hypervisor resource management** because it lacks a state model and idempotent plan/apply semantics.

OpenTofu (the open-source Terraform fork) with the `bpg/proxmox` provider gives us exactly this: a plan that shows what will change before applying it, a state file that tracks actual resources, and drift detection on every run.

## Decision

We will introduce **OpenTofu** (`tofu`) for all Proxmox resource management and move VM lifecycle out of Ansible.

### Scope boundary

| Concern | Tool |
|---|---|
| Proxmox VMs: create, resize, destroy, network, snapshots | **OpenTofu** |
| Configuration inside a VM: packages, services, files, users | **Ansible** |
| VM template creation | **Packer** (ADR 0084) |
| Secret injection into Compose stacks | **OpenBao** (ADR 0077) |

### Directory structure

```
tofu/
  modules/
    proxmox-vm/            # reusable VM module
      main.tf
      variables.tf
      outputs.tf
    proxmox-lxc/           # LXC containers (future)
    proxmox-network/       # bridges, VLANs
  environments/
    production/
      main.tf              # declares all prod VMs
      terraform.tfvars     # non-secret values
      backend.tf           # remote state config
    staging/
      main.tf
      terraform.tfvars
      backend.tf
  .terraform.lock.hcl
```

### Remote state backend

State configuration is committed in `tofu/environments/*/backend.tf` and targets the internal S3-compatible object store at `https://minio.example.com` with `use_lockfile = true`. The execution wrapper automatically uses the remote backend when `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are provided at runtime; otherwise it falls back to build-server local state under `~/.cache/lv3-tofu-plans/` so validation, import, and drift checks still work without storing backend credentials in git.

### `proxmox-vm` module interface

```hcl
module "docker_runtime" {
  source       = "../../modules/proxmox-vm"
  name         = "docker-runtime"
  vmid         = 110
  template     = "lv3-docker-host"       # Packer template (ADR 0084)
  cores        = 4
  memory_mb    = 8192
  disk_gb      = 80
  ip_address   = "10.10.10.20/24"
  gateway      = "10.10.10.1"
  bridge       = "vmbr10"
  tags         = ["docker", "production"]
  startup_order = 2
}
```

### Authentication

OpenTofu authenticates to Proxmox using a short-lived API token issued via OpenBao (ADR 0047). The token is injected at plan/apply time by `make remote-tofu-plan` / `make remote-tofu-apply` via the remote execution gateway (ADR 0082). Tokens are never stored in the repository or state file.

Current implementation detail: remote `tofu` runs execute inside the pinned infra check-runner image with Docker host networking enabled on `build-lv3`, because the container path could not reliably resolve `proxmox.example.com` over the default bridge network during live import verification.

### make targets

| Target | Action |
|---|---|
| `make remote-tofu-plan ENV=production` | `tofu plan` on build server, output saved as artifact |
| `make remote-tofu-apply ENV=production` | `tofu apply` with saved plan (requires operator approval gate) |
| `make remote-tofu-plan ENV=staging` | plan for staging environment |
| `make tofu-import VM=<name>` | import existing VM into state (migration path) |
| `make tofu-drift ENV=production` | runs `tofu plan` and exits non-zero if drift detected |

### Migration path

Existing VMs are imported into the OpenTofu state using `make tofu-import` before any new resources are declared. This produces a state file that matches reality without destroying and recreating VMs. The import process is documented in `docs/runbooks/tofu-vm-import.md`.

## Implementation Notes

- `tofu/modules/proxmox-vm/` is implemented and used by both `production` and `staging`.
- `make remote-tofu-plan`, `make remote-tofu-apply`, `make tofu-drift`, and `make tofu-import` are implemented through `scripts/tofu_exec.sh` and `scripts/tofu_remote_command.py`.
- Production currently tracks the six live guest VMs `110`, `120`, `130`, `140`, `150`, and `160`.
- `make tofu-import ENV=production VM=<name>` was verified for all six production VMs on `build-lv3`.
- `make tofu-drift ENV=production` was verified against the imported production state and returns `No changes`.
- `make remote-tofu-plan ENV=staging` was verified on `build-lv3` and returns a create-only plan for the staging VMs.
- Because the `bpg/proxmox` provider does not round-trip every imported field cleanly, the module ignores import-only drift on `clone`, `node_name`, `keyboard_layout`, and `agent.type` to keep imported production VMs stable under drift checks.

## Consequences

**Positive**
- Plan output shows exactly what will change before any Proxmox mutation — eliminates surprise VM changes
- State file is the authoritative record of VM resource allocation; `stack.yaml` becomes a derived view
- Drift detection (`make tofu-drift`) can run on a schedule and emit a NATS event if actual state diverges from declared state
- Staging and production are separate state files; a staging VM misconfiguration cannot accidentally affect production
- VM resizing is now a declarative PR: change `memory_mb` in `main.tf`, open PR, review plan output, merge

**Negative / Trade-offs**
- Importing existing VMs into state is a one-time migration effort and depends on provider import quality
- OpenTofu state in MinIO is a new dependency; MinIO must be available for any `tofu` operation
- Operators need basic HCL familiarity; a short onboarding doc is required
- `bpg/proxmox` provider occasionally lags behind Proxmox API changes; pin provider version strictly
- Imported Proxmox VMs currently require a small ignore list for provider-populated fields that otherwise cause false drift or forced replacement after import

## Alternatives Considered

- **Pulumi**: supports Python; higher complexity for a solo/small team; stronger opinion on programming language
- **Continue with Ansible for VM lifecycle**: works but no plan semantics, no state model; drift accumulates silently
- **Proxmox SDN + manual config**: Proxmox-native but not source-controlled, not reproducible

## Related ADRs

- ADR 0072: Staging/production topology (OpenTofu manages both environments as separate state)
- ADR 0082: Remote build execution gateway (`tofu` runs on build server)
- ADR 0083: Docker check runner (infra image includes `tofu` binary)
- ADR 0084: Packer template pipeline (templates are the source for `template =` in VM modules)
- ADR 0088: Ephemeral infrastructure fixtures (uses OpenTofu to spin up/tear down test VMs)
- ADR 0091: Drift detection (`make tofu-drift` is one of the drift sources)
