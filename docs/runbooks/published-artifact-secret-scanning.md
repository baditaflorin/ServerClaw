# Published Artifact Secret Scanning

## Purpose

This runbook covers ADR 0138's published-artifact secret scan for repo-managed receipts and generated publication outputs.

## Repo Surfaces

- `scripts/published_artifact_secret_scan.py`
- `.gitleaks.toml`
- `config/validation-gate.json`
- `Makefile`

## Scanned Paths

By default the scanner checks:

- `receipts/**/*.json`
- `.local/triage/reports/**/*.json`
- `build/search-index/**/*.json`
- `build/changelog-portal/**/*.html`
- `build/changelog-portal/**/*.json`

## Manual Command

Run the dedicated target from a checkout:

```bash
make scan-published-artifacts
```

Or invoke the script directly:

```bash
python3 scripts/published_artifact_secret_scan.py --repo-root /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
```

Scan a specific path only:

```bash
python3 scripts/published_artifact_secret_scan.py --repo-root /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server --path build/changelog-portal
```

## Gate Integration

The blocking validation-gate stage is `artifact-secret-scan` in `config/validation-gate.json`.

It runs inside the security check-runner image, where `gitleaks` is available, so gate execution uses the full `.gitleaks.toml` rule set.

## Artifact Generation Flow

These targets now scan immediately after writing their outputs:

- `make search-index-rebuild`
- `make generate-changelog-portal`

If the scan fails, treat the artifact as tainted:

1. inspect the listed file path
2. redact the secret-bearing field or remove the artifact
3. rerun the generating command
4. rerun `make scan-published-artifacts`

## Verification

1. `python3 -m pytest tests/test_published_artifact_secret_scan.py tests/test_validation_gate.py -q`
2. create a disposable dummy receipt containing a fake `hvs.` token
3. run `python3 scripts/published_artifact_secret_scan.py --repo-root ... --path receipts/live-applies`
4. confirm the command exits non-zero and reports the file path
