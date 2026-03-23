# Packer VM Templates

ADR 0084 introduces a repo-managed Packer pipeline for the Proxmox guest template catalog.

## Repo Surfaces

- `packer/templates/` defines the layered template builders:
  - `lv3-debian-base`
  - `lv3-docker-host`
  - `lv3-postgres-host`
  - `lv3-ops-base`
- `packer/scripts/` holds the provisioning scripts applied during each build.
- `packer/variables/common.pkrvars.hcl` holds the shared Proxmox and build defaults.
- `packer/variables/<template>.pkrvars.hcl` holds template-specific VMIDs, names, and bootstrap inputs.
- `config/vm-template-manifest.json` records the intended VMIDs plus the most recent rebuild metadata.
- `config/windmill/scripts/packer-template-rebuild.py` is the Windmill-facing orchestration entrypoint.

## Prerequisites

1. `make check-build-server` passes.
2. The build worker has `packer` installed and can reach the Proxmox API.
3. Proxmox API credentials are available either as:
   - `PKR_VAR_proxmox_api_token_id`
   - `PKR_VAR_proxmox_api_token_secret`
   or through an OpenBao session:
   - `OPENBAO_ADDR`
   - `OPENBAO_TOKEN`
4. The bootstrap source template referenced by `packer/variables/lv3-debian-base.pkrvars.hcl` exists before the first `lv3-debian-base` rebuild.

## Validate Templates

Run the repository-managed validation wrapper:

```bash
make validate-packer
```

This calls `scripts/validate_packer_templates.sh`, which runs `packer init` and `packer validate` for every template under `packer/templates/` using the shared, template-specific, and build-server var-files.

## Rebuild One Template

Use the build-server gateway:

```bash
make remote-packer-build IMAGE=lv3-debian-base
make remote-packer-build IMAGE=lv3-docker-host
make remote-packer-build IMAGE=lv3-postgres-host
make remote-packer-build IMAGE=lv3-ops-base
```

The `IMAGE` must match one of the template file basenames in `packer/templates/`.

## Rebuild The Full Catalog

Run the Windmill helper from a credentialed checkout:

```bash
export PKR_VAR_proxmox_api_token_id="lv3-automation@pve!primary"
export PKR_VAR_proxmox_api_token_secret="..."
python3 config/windmill/scripts/packer-template-rebuild.py
```

The helper rebuilds templates in dependency order and writes `build_date`, `version`, `digest`, and `packer_commit` back into `config/vm-template-manifest.json`.

## Consumer Model

Managed guests now declare `template_key` in [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml), and [roles/proxmox_guests/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/ansible_collections/lv3/platform/roles/proxmox_guests/tasks/main.yml) clones from the corresponding `proxmox_vm_templates` entry instead of creating a Debian cloud template inline.

## Failure Notes

- If `make validate-packer` fails during `packer init`, clear or inspect the build-worker plugin cache under `/opt/builds/.packer.d`.
- If `make remote-packer-build` fails before connecting to Proxmox, check that `PKR_VAR_proxmox_api_token_*` variables are present and that `scripts/remote_exec.sh` can SSH to `docker-build-lv3`.
- If the first `lv3-debian-base` rebuild conflicts with an existing bootstrap template VMID, adjust the bootstrap source before promoting the Packer-managed template into the canonical VMID.
