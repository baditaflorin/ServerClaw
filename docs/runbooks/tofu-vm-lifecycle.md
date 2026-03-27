# OpenTofu VM Lifecycle

Use this runbook for routine Proxmox VM lifecycle operations managed through OpenTofu.

## Validate

```bash
make validate-tofu
```

## Plan Staging

```bash
make remote-tofu-plan ENV=staging
```

Expected result:

- the plan is generated on `build-lv3`
- the saved plan and JSON artifact are written under `/home/ops/.cache/lv3-tofu-plans/`
- the plan shows create-only actions for the declared staging VMs unless state already exists

## Check Production Drift

```bash
make tofu-drift ENV=production
```

Expected result:

- exit code `0` means no drift
- exit code `2` means the production declarations and imported state diverged and must be reviewed before any apply

## Apply A Reviewed Plan

```bash
make remote-tofu-plan ENV=production
make remote-tofu-apply ENV=production
```

Only run `remote-tofu-apply` after reviewing the saved plan. Production resources keep `prevent_destroy = true`, so a replacement plan should fail instead of deleting a VM silently.

## Backend Activation

The repository commits MinIO-backed `backend.tf` files, but backend credentials are injected at runtime rather than stored in git.

To activate the shared backend for a run, export:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
```

Without those variables, the wrapper uses build-server local state so validation and import workflows still function.
