# Reference Deployment Samples Runbook

## Purpose

This runbook defines the ADR 0339 workflow for starting a new fork from
reference deployment samples and replaceable provider profiles.

## Canonical Sources

Edit these files directly:

- `reference-deployments/catalog.yaml`
- `config/reference-provider-profiles.yaml`
- `reference-deployments/templates/`

Do not treat rendered output as canonical repo truth. The rendered files are
starter material for a new fork or lab checkout.

## Standard Flow

1. Choose a sample from `reference-deployments/catalog.yaml`.
2. Choose a provider profile from `config/reference-provider-profiles.yaml`.
3. Render the starter files into a clean output directory:

```bash
uv run --with pyyaml python3 scripts/reference_deployment_samples.py render \
  --sample single-node-proxmox-lab \
  --profile dedicated-public-edge \
  --output-dir /tmp/reference-platform
```

4. Replace the example values before the first live mutation:

- host labels and inventory hostnames
- provider hostnames and public domains
- example IP addresses
- private overlay file paths and bootstrap secrets

5. Validate the committed sample sources whenever the templates or profiles change:

```bash
uv run --with pyyaml python3 scripts/reference_deployment_samples.py validate
```

## Rendered Output Contract

The render command currently writes:

- `inventory/hosts.yml`
- `inventory/host_vars/reference-proxmox.yml`
- `config/api-publication.json`
- `.local/reference-deployment/controller-local-secrets.json`
- `.reference-deployment-render.json`

The `.local/` path is intentionally private overlay state and should remain
uncommitted in the new fork.

## What The Validator Enforces

- every sample points at real canonical example files in the repo
- every template source exists and every destination path stays repository-relative
- provider profile values remain example-safe rather than deployment-specific
- each sample can render successfully for every declared provider profile
- the rendered inventory, publication sample, and local secret overlay pass the
  starter-contract checks

## Notes

- These samples are intentionally smaller than the live production catalogs.
  They are meant to be a guided bootstrap path, not a mirror of every current
  platform detail.
- If a real automation contract changes, update the sample catalog and its
  templates in the same turn so the example path stays believable.
