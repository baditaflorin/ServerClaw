# OpenTofu VM Import

Use this runbook to import already-running Proxmox VMs into the OpenTofu production state without recreating them.

## Preconditions

- controller-local Proxmox token payload exists at `.local/proxmox-api/lv3-automation-primary.json`
- `build-lv3` is reachable through the remote execution gateway
- production VM declarations under `tofu/environments/production/main.tf` match the intended VMIDs, MAC addresses, IPs, and tags

If `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are exported when running the commands below, `tofu` uses the configured MinIO backend. If they are absent, the wrapper falls back to build-server local state under `/home/ops/.cache/lv3-tofu-plans/production.tfstate`.

## Import Sequence

Validate the OpenTofu configuration first:

```bash
make validate-tofu
```

Import the production VMs one at a time:

```bash
make tofu-import ENV=production VM=nginx-lv3
make tofu-import ENV=production VM=docker-runtime-lv3
make tofu-import ENV=production VM=docker-build-lv3
make tofu-import ENV=production VM=monitoring-lv3
make tofu-import ENV=production VM=postgres-lv3
make tofu-import ENV=production VM=backup-lv3
```

Verify that the imported state matches the current platform:

```bash
make tofu-drift ENV=production
```

Expected result:

- `make tofu-import` succeeds for each VMID
- `make tofu-drift ENV=production` reports `No changes`

## Notes

- The remote command wrapper forces Docker host networking for the infra runner so the containerized `tofu` process can reach the Proxmox API reliably from `build-lv3`.
- Production imports rely on module-level `prevent_destroy` plus targeted ignore rules for provider-populated import fields (`clone`, `node_name`, `keyboard_layout`, and `agent.type`).
- If a production drift run proposes replacement, stop and inspect the imported state before applying anything.
