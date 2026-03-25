# Public Surface Security Scan

This runbook covers the ADR 0142 workflow that validates the public HTTP or HTTPS surface from the outside.

## Repo Surfaces

- `config/public-surface-scan-policy.json`
- `scripts/public_surface_scan.py`
- `config/windmill/scripts/weekly-security-scan.py`
- `config/workflow-catalog.json`
- `config/control-plane-lanes.json`
- `receipts/security-scan/`

## Local Execution

Run the controller-side scan:

```bash
make public-surface-security-scan ENV=production
```

Or call the Python entrypoint directly:

```bash
python3 scripts/public_surface_scan.py --env production --print-report-json
```

The workflow:

1. discovers active public HTTPS hostnames from `config/subdomain-catalog.json`
2. evaluates required security headers and version disclosure on the unauthenticated response
3. checks OIDC-protected public hostnames for the expected redirect to `sso.lv3.org`
4. runs `testssl.sh` against each hostname
5. runs `nuclei` redirect and misconfiguration templates against `https://lv3.org`
6. writes a receipt under `receipts/security-scan/`

## Outputs

Each receipt records:

- the scanned hostname set
- per-host HTTP observations
- `testssl.sh` raw artifact paths
- the `nuclei` raw artifact path
- categorized findings by severity and component
- an aggregate summary for operator review and optional event publication

Raw tool artifacts are stored under `.local/public-surface-scan/<scan_id>/`.

## Optional Publication

When the relevant environment variables or controller-local secret files are present, the workflow can:

- publish `platform.security.*` events over NATS
- post the weekly summary to Mattermost
- forward CRITICAL findings to GlitchTip

## Verification

Use these checks after a run:

```bash
python3 -m py_compile scripts/public_surface_scan.py config/windmill/scripts/weekly-security-scan.py
python3 scripts/public_surface_scan.py --env production --skip-testssl --skip-nuclei --print-report-json
uv run --with pytest --with pyyaml --with nats-py pytest -q tests/test_public_surface_scan.py
```

Confirm:

- the newest file under `receipts/security-scan/` is valid JSON
- the receipt target set matches the active public HTTPS entries in the subdomain catalog
- the artifacts directory for that `scan_id` contains any requested `testssl.sh` or `nuclei` raw outputs
- high or critical findings are present on `platform.security.*` only when publication is enabled
