# Reference Deployment Samples

This directory holds the ADR 0339 example-first bootstrap assets for new forks.

Use these sources when you need to answer three questions quickly:

- which committed files are the canonical examples for a new deployment
- which provider, publication, and local-overlay values are meant to be replaced
- what a fresh controller-local bootstrap output should look like before the first live mutation

## Canonical Sources

- `reference-deployments/catalog.yaml`
- `config/reference-provider-profiles.yaml`
- `reference-deployments/templates/`
- `docs/runbooks/reference-deployment-samples.md`

## Primary Commands

Validate the committed sources:

```bash
uv run --with pyyaml python3 scripts/reference_deployment_samples.py validate
```

Render one sample into a clean output directory:

```bash
uv run --with pyyaml python3 scripts/reference_deployment_samples.py render \
  --sample single-node-proxmox-lab \
  --profile dedicated-public-edge \
  --output-dir /tmp/reference-platform
```

The rendered output is intentionally starter material, not live truth. Keep the
rendered `.local/` overlay outside git and replace the example values before the
first real deployment.
