# Workstream ADR 0085: OpenTofu VM Lifecycle

- ADR: [ADR 0085](../adr/0085-opentofu-vm-lifecycle.md)
- Title: Declarative VM provisioning with OpenTofu replacing ad-hoc Ansible VM creation tasks
- Status: ready
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

## Expected Live Surfaces

- MinIO bucket `tofu-state/production/` contains valid state file matching all 8 production VMs
- `make tofu-drift ENV=production` exits 0 (no unplanned changes) after import
- `make remote-tofu-plan ENV=staging` produces a clean plan showing the staging VM declarations

## Verification

- `make tofu-drift ENV=production` exit 0 on a fresh build server run
- `tofu show` for each production VM matches the values in `versions/stack.yaml`
- `make remote-tofu-plan ENV=staging` produces a parseable JSON plan with no errors

## Merge Criteria

- all 8 production VMs imported into state; `tofu plan` shows "No changes" for production
- state file exists in MinIO and is readable by a second build server workspace (shared state confirmed)
- `make tofu-import VM=<name>` runbook verified against one real VM as a smoke test

## Notes For The Next Assistant

- the `bpg/proxmox` provider requires the Proxmox API URL and token; use the same OpenBao path as the Packer pipeline; document the exact OpenBao path in `tofu/modules/proxmox-vm/README.md`
- during the import phase, run `tofu import` in `--target` mode one VM at a time; do not run a bulk import; each import should be followed by `tofu plan` to verify zero drift before importing the next
- add `lifecycle { prevent_destroy = true }` to all production VM resources as a safeguard; an accidental `tofu destroy` must never be possible without removing the lifecycle block explicitly
