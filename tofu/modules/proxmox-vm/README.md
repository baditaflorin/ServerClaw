# proxmox-vm

Reusable OpenTofu module for Proxmox VM lifecycle management.

Inputs cover the stable VM identity and allocation surfaces this repository tracks today:

- VMID, node name, template VMID, and datastore ids
- CPU, memory, disk, bridge, MAC address, and startup order
- cloud-init IPv4/DNS settings
- optional existing `user_data_file_id` for imported production guests

Authentication is provided at execution time, not in HCL:

- current repo entry points read the controller-local Proxmox token payload from `.local/proxmox-api/lv3-automation-primary.json`
- the intended secret source remains OpenBao path `secret/build-server/proxmox-api-token`
- `scripts/tofu_remote_command.py` converts the payload into `TF_VAR_proxmox_endpoint` and `TF_VAR_proxmox_api_token` exports for `scripts/tofu_exec.sh`
- remote `tofu` runs force Docker host networking on `build-lv3` so the containerized runner can reach the Proxmox API reliably during import and drift checks

All managed VMs include `lifecycle { prevent_destroy = true }` so a destructive action requires an explicit config change first.

Imported production VMs also ignore provider-populated drift on `clone`, `node_name`, `keyboard_layout`, and `agent.type` because those fields do not currently round-trip cleanly through `bpg/proxmox` imports.
