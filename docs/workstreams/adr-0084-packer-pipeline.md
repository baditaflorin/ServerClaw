# Workstream ADR 0084: Packer VM Template Pipeline

- ADR: [ADR 0084](../adr/0084-packer-vm-template-pipeline.md)
- Title: Automated, layered Packer VM templates on the build server for fast, consistent Proxmox VM provisioning
- Status: merged
- Branch: `codex/adr-0084-packer-vm-template-pipeline`
- Worktree: `../proxmox_florin_server-adr-0084`
- Owner: codex
- Depends On: `adr-0082-remote-build-gateway`, `adr-0083-docker-check-runner`
- Conflicts With: none
- Shared Surfaces: `Makefile`, `inventory/`, Proxmox storage pool, `config/`

## Scope

- create `packer/` directory structure: `templates/`, `scripts/`, `variables/`
- write four `.pkr.hcl` template files: `lv3-debian-base`, `lv3-docker-host`, `lv3-postgres-host`, `lv3-ops-base`
- write Packer provisioner shell scripts: `base-hardening.sh`, `docker-install.sh`, `postgres-install.sh`, `step-cli-install.sh`
- write `variables/common.pkrvars.hcl`, `variables/build-server.pkrvars.hcl`, and per-template `variables/*.pkrvars.hcl`
- write `config/vm-template-manifest.json` — tracks template VMID, build date, version, and Packer commit SHA
- add `make remote-packer-build IMAGE=<name>` target
- write Windmill workflow `packer-template-rebuild` — triggers on `packer/` changes and weekly at 02:00 Sunday
- update Ansible VM-create tasks to use `clone: "lv3-docker-host"` instead of raw cloud image upload
- write `docs/runbooks/packer-vm-templates.md`

## Non-Goals

- LXC template builds (VMs only for now)
- Windows VM templates

## Expected Repo Surfaces

- `packer/templates/*.pkr.hcl` (4 files)
- `packer/scripts/*.sh` (4 provisioner scripts)
- `packer/variables/*.pkrvars.hcl`
- `config/vm-template-manifest.json`
- updated `Makefile` (`remote-packer-build`, `validate-packer`)
- updated `roles/*/tasks/main.yml` for roles that create VMs (use template clone)
- Windmill script `config/windmill/scripts/packer-template-rebuild.py`
- `docs/runbooks/packer-vm-templates.md`
- `docs/adr/0084-packer-vm-template-pipeline.md`
- `docs/workstreams/adr-0084-packer-pipeline.md`
- `workstreams.yaml`

## Expected Live Surfaces

- four Proxmox templates at VMIDs 9000–9003 named `lv3-{debian-base,docker-host,postgres-host,ops-base}`
- `make remote-packer-build IMAGE=lv3-debian-base` completes in < 20 min on a warm cache
- new VM provisioning time from clone < 5 min (verified against docker_runtime role)

## Verification

- boot a VM cloned from `lv3-docker-host` and verify: `docker ps` works, `step version` works, SSH hardening config present
- `config/vm-template-manifest.json` contains non-empty `digest` and `build_date` for all four templates
- Packer `validate` passes for all four templates via `make validate-packer` on the build server

## Completion Notes

- the repository now carries the full Packer layout under [packer/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-adr-0084/packer), the template manifest under [config/vm-template-manifest.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-adr-0084/config/vm-template-manifest.json), and the Windmill rebuild helper at [config/windmill/scripts/packer-template-rebuild.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-adr-0084/config/windmill/scripts/packer-template-rebuild.py)
- [roles/proxmox_guests/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-adr-0084/roles/proxmox_guests/tasks/main.yml) now clones guests from the declared template catalog instead of constructing a Debian cloud template inline
- the remaining operational step is live rebuild and publication of the templates from a credentialed worker so the manifest gains populated `build_date` and `digest` values

## Merge Criteria

- all four templates build successfully end-to-end on the build server
- `make remote-packer-build IMAGE=lv3-debian-base` completes and the resulting template is queryable via Proxmox API
- Ansible VM-create tasks updated for at least one role to use the new template (proof of concept)

## Notes For The Next Assistant

- the `bpg/proxmox` Packer provider requires the Proxmox API URL, API token ID, and API token secret; these must be fetched from OpenBao at build time — add an `openbao_lookup` step at the start of the Windmill workflow
- Packer's Proxmox provider can be slow to report template creation; add a `wait_for` with a 10-minute timeout in the HCL
- `base-hardening.sh` should mirror the tasks in the `common` Ansible role exactly; add a comment block at the top of both files noting they must stay in sync until ADR 0086 (collection packaging) lands
