# Security Posture Reporting

This runbook covers the ADR 0102 security posture workflow that combines Lynis host scans with Trivy runtime image scans.

## Repo Surfaces

- `playbooks/tasks/security-scan.yml`
- `scripts/parse_lynis_report.py`
- `scripts/trivy_scan_running_images.sh`
- `scripts/security_posture_report.py`
- `config/windmill/scripts/security-posture-scan.py`
- `config/lynis-suppressions.json`
- `receipts/security-reports/`

## Local Execution

Run the full workflow from the controller checkout:

```bash
make security-posture-report
```

Or call the Python entrypoint directly:

```bash
python3 scripts/security_posture_report.py --env production --print-report-json
```

The workflow:

1. runs `playbooks/tasks/security-scan.yml` against the repo-managed Lynis targets
2. fetches each `report.dat` file into `.local/security-posture/lynis/`
3. parses and suppresses known-acceptable Lynis findings
4. SSHes to `docker-runtime-lv3` and `docker-build-lv3` and runs `scripts/trivy_scan_running_images.sh`
5. compares the new scan to the latest committed receipt in `receipts/security-reports/`
6. writes a new JSON receipt under `receipts/security-reports/`

## Outputs

Each receipt records:

- per-host hardening index
- per-host Lynis finding counts and new findings since the previous receipt
- per-image HIGH and CRITICAL CVEs
- an aggregate summary for portal and dashboard consumption

When the relevant environment variables or controller-local secret files are present, the workflow also:

- publishes `platform.security.*` NATS events
- posts a summary to Mattermost
- posts critical findings to GlitchTip
- writes `platform_security_posture_*` metrics to InfluxDB

## Suppressions

Known-acceptable Lynis findings live in `config/lynis-suppressions.json`.

Add a suppression only when:

- the finding is persistent across scans
- the condition is understood
- the platform intentionally accepts the risk or cannot remediate it in repo automation yet

Prefer suppressing by Lynis finding id, not by raw text.

## Verification

Use these checks after a run:

```bash
python3 scripts/parse_lynis_report.py .local/security-posture/lynis
python3 scripts/security_posture_report.py --env production --print-report-json
```

Confirm:

- the newest file under `receipts/security-reports/` is valid JSON
- each expected host has a hardening index
- each Docker host contributed image scan data
- the ops portal shows the latest security receipt summary
