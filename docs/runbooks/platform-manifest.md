# Platform Manifest

This runbook covers the repo-generated platform manifest introduced by ADR 0132.

## Purpose

The manifest is the single machine-readable summary of the platform's current repository-tracked shape:

- identity and version metadata
- service health posture derived from repo evidence or live SLO metrics
- active incident and maintenance context when local inputs are available
- governed workflow and runbook capability summaries
- registered automation identities and known ADR gaps

The committed artifact lives at `build/platform-manifest.json`.

## Source Inputs

The generator reads from:

- `config/manifest-static.yaml`
- `config/service-capability-catalog.json`
- `config/workflow-catalog.json`
- `config/workflow-defaults.yaml`
- `versions/stack.yaml`
- `docs/adr/`
- `docs/runbooks/`
- `docs/release-notes/`
- `receipts/live-applies/`

Optional local inputs:

- Prometheus via `--prometheus-url` for live SLO-backed health
- `.local/triage/reports/` for open incident summaries
- `LV3_MAINTENANCE_WINDOWS_FILE` or live NATS access for active maintenance windows

## Generate

Write the canonical artifact:

```bash
uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --write
```

Write a temporary copy without touching the committed artifact:

```bash
uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --output /tmp/platform-manifest.json
```

Use live Prometheus data when available:

```bash
uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --write --prometheus-url http://127.0.0.1:9090
```

## Verify

Check schema compliance and artifact drift:

```bash
uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check
```

Inspect the rendered summary through the CLI:

```bash
python scripts/lv3_cli.py manifest show
python scripts/lv3_cli.py manifest show --json
```

Force a local refresh from the CLI:

```bash
python scripts/lv3_cli.py manifest refresh
```

## Notes

- When Prometheus is not available, health falls back to repo evidence. The manifest records this in `health.mode`.
- When no local triage reports or maintenance state are available, `incidents.items` and `maintenance.active_windows` remain empty instead of failing generation.
- The validation gate treats the committed JSON as generated output. If source catalogs or ADR metadata change, rerun the generator in the same change.
