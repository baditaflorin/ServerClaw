# Run Namespace Partitioning

ADR 0177 makes mutable controller-side tooling write into:

```text
.local/runs/<run_id>/
```

Use this runbook when you need predictable, isolated scratch space for live apply, dry-run, or OpenTofu work.

## Layout

Each run namespace reserves:

- `.local/runs/<run_id>/ansible/`
- `.local/runs/<run_id>/tofu/`
- `.local/runs/<run_id>/rendered/`
- `.local/runs/<run_id>/logs/`
- `.local/runs/<run_id>/receipts/`

The repository now resolves these paths with [scripts/run_namespace.py](/Users/live/Documents/GITHUB_PROJECTS/worktree-adr-0177-namespace-partitioning/scripts/run_namespace.py).

## Common Usage

For one-shot live apply commands, let the Makefile generate a fresh `RUN_ID`:

```bash
make live-apply-service service=api-gateway env=production
```

For repeated OpenTofu operations that must share one saved plan, pin the `RUN_ID` yourself and reuse it:

```bash
RUN_ID=adr-0177-prod-plan make remote-tofu-plan ENV=production
RUN_ID=adr-0177-prod-plan make remote-tofu-apply ENV=production
```

For direct inspection of the resolved namespace:

```bash
python3 scripts/run_namespace.py --run-id adr-0177-demo --ensure
```

## What Is Scoped

- Ansible local temp files, retry files, SSH control paths, and logs
- OpenTofu plan files and runtime copies used during `init`, `plan`, `apply`, `drift`, `import`, and `show`
- diff-engine and drift-detector subprocess scratch paths
- forwarded `LV3_RUN_ID` for remote build-server OpenTofu commands

## Cleanup

Run namespaces are disposable after the related investigation or apply finishes.

Review the current namespace roots:

```bash
find .local/runs -mindepth 1 -maxdepth 1 -type d | sort
```

Remove stale namespaces when you no longer need their local logs or plan bundles:

```bash
rm -rf .local/runs/<run_id>
```

Do not delete a namespace while a live apply, drift check, or OpenTofu plan/apply pair is still using it.
