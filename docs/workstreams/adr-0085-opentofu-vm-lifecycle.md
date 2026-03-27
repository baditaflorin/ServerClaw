# Workstream ADR 0085: OpenTofu VM Lifecycle

- ADR: [ADR 0085](../adr/0085-opentofu-vm-lifecycle.md)
- Title: Declarative VM provisioning with OpenTofu replacing ad-hoc Ansible VM creation tasks
- Status: merged
- Branch: `codex/adr-0085-opentofu-vm-lifecycle`
- Worktree: `../proxmox_florin_server-opentofu-vm-lifecycle`
- Owner: codex
- Depends On: `adr-0082-remote-build-gateway`, `adr-0083-docker-check-runner`, `adr-0084-packer-pipeline`
- Conflicts With: roles that contain `community.general.proxmox_kvm` create tasks
- Shared Surfaces: `Makefile`, `inventory/`, `config/`, MinIO state backend, Proxmox API

## Scope

- create `tofu/` directory: `modules/proxmox-vm/`, `environments/production/`, `environments/staging/`
- write `modules/proxmox-vm/main.tf`, `variables.tf`, `outputs.tf` — reusable VM module with all standard fields
- write `environments/production/main.tf` declaring all current production VMs (imported, not recreated)
- write `environments/staging/main.tf` with staging VM declarations (from ADR 0072)
- write `environments/*/backend.tf` pointing to MinIO state backend
- add `make remote-tofu-plan ENV=<env>`, `make remote-tofu-apply ENV=<env>`, `make tofu-drift ENV=<env>`, `make tofu-import VM=<name>` targets
- write `docs/runbooks/tofu-vm-import.md` — step-by-step import guide for all 8 existing production VMs
- execute the import: run `make tofu-import` for each existing VM, producing a clean state file with no planned changes
- write `docs/runbooks/tofu-vm-lifecycle.md` — day-to-day usage guide

## Non-Goals

- OpenTofu for non-VM Proxmox resources (storage pools, SDN) — deferred
- removing all Ansible `proxmox_kvm` tasks (only new VM creation is moved; existing playbooks updated not removed)

## Expected Repo Surfaces

- `tofu/modules/proxmox-vm/{main,variables,outputs}.tf`
- `tofu/environments/production/{main,backend}.tf` + `terraform.tfvars`
- `tofu/environments/staging/{main,backend}.tf` + `terraform.tfvars`
- `.terraform.lock.hcl` committed per environment
- updated `Makefile` (4 new tofu targets)
- `docs/runbooks/tofu-vm-import.md`
- `docs/runbooks/tofu-vm-lifecycle.md`
- `docs/adr/0085-opentofu-vm-lifecycle.md`
- `docs/workstreams/adr-0085-opentofu-vm-lifecycle.md`
- `workstreams.yaml`

## Observed Live Surfaces

- the production declarations now cover the six live VMs `110`, `120`, `130`, `140`, `150`, and `160`
- `make tofu-import ENV=production VM=<name>` was verified against all six production VMs on `build-lv3`
- `make tofu-drift ENV=production` exits `0` with `No changes`
- `make remote-tofu-plan ENV=staging` produces a valid create-only plan for the declared staging VMs
- MinIO backend configuration is committed, with runtime fallback to build-server local state when backend credentials are not injected

## Verification

- `make tofu-drift ENV=production` exit 0 on a fresh build server run
- `tofu state show` for each imported production VM matches the declared VMID, MAC, IP, and tag surfaces
- `make remote-tofu-plan ENV=staging` produces a parseable JSON plan with no errors

## Outcome

- the OpenTofu VM module and both environment trees are implemented
- the remote wrapper uses the pinned infra check-runner image plus host networking on `build-lv3`
- provider import quirks are isolated through module-level ignore rules so imported production VMs do not plan replacement
- production import and drift are verified; staging planning is verified
