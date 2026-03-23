# Workstream ADR 0102: Security Posture Reporting and Benchmark Drift

- ADR: [ADR 0102](../adr/0102-security-posture-reporting.md)
- Title: Weekly Lynis host hardening scans and Trivy container image CVE scans with results in the ops portal, GlitchTip, and Mattermost
- Status: ready
- Branch: `codex/adr-0102-security-posture`
- Worktree: `../proxmox_florin_server-security-posture`
- Owner: codex
- Depends On: `adr-0006-security-baseline`, `adr-0024-docker-security`, `adr-0044-windmill`, `adr-0057-mattermost`, `adr-0061-glitchtip`, `adr-0066-audit-log`, `adr-0068-image-policy`, `adr-0087-validation-gate`, `adr-0093-interactive-ops-portal`, `adr-0097-alerting-routing`
- Conflicts With: none
- Shared Surfaces: `playbooks/tasks/`, `scripts/`, `config/grafana/dashboards/`, `receipts/`

## Scope

- write `playbooks/tasks/security-scan.yml` — Ansible playbook that runs Lynis on target hosts and fetches reports
- write `scripts/parse_lynis_report.py` — parses Lynis `.dat` report into structured JSON
- write `scripts/trivy_scan_running_images.sh` — scans all running containers on `docker-runtime-lv3` via Trivy
- write `scripts/security_posture_report.py` — aggregates Lynis and Trivy results into a unified report JSON
- write Windmill workflow `security-posture-scan` — scheduled Monday 01:00 UTC; orchestrates all scans
- write `config/lynis-suppressions.json` — known-acceptable Lynis findings to suppress from reporting
- add `receipts/security-reports/.gitkeep`
- add Grafana panel `Security Posture` to platform overview dashboard (`config/grafana/dashboards/platform-overview.json`)
- add Grafana alert: hardening index drops > 10 points from previous week → warning alert
- add security posture summary endpoint to API gateway (`/v1/platform/security-posture`)
- install Lynis on all target VMs via `roles/security_baseline/` (patch existing role)
- install Trivy on `docker-build-lv3` via a new task in `roles/docker_build_server/` or a dedicated role

## Non-Goals

- Automated remediation of Lynis findings
- MEDIUM/LOW CVE reporting from Trivy (HIGH/CRITICAL only)
- Compliance reporting against specific frameworks (SOC2, ISO 27001) in this iteration

## Expected Repo Surfaces

- `playbooks/tasks/security-scan.yml`
- `scripts/parse_lynis_report.py`
- `scripts/trivy_scan_running_images.sh`
- `scripts/security_posture_report.py`
- `config/lynis-suppressions.json`
- `receipts/security-reports/.gitkeep`
- `config/grafana/dashboards/platform-overview.json` (patched: Security Posture panel)
- `roles/security_baseline/` (patched: Lynis installation task)
- `docs/adr/0102-security-posture-reporting.md`
- `docs/workstreams/adr-0102-security-posture-reporting.md`

## Expected Live Surfaces

- Windmill `security-posture-scan` workflow has at least one successful run
- `receipts/security-reports/` contains at least one report JSON
- Grafana platform overview shows Security Posture panel with hardening index bars
- Mattermost `#platform-security` channel received the weekly scan summary

## Verification

- Trigger `security-posture-scan` workflow manually
- Verify `receipts/security-reports/<date>.json` is written with all 5 hosts' Lynis results
- Verify Trivy results are included for all running containers on `docker-runtime-lv3`
- Mattermost `#platform-security` received the scan summary
- Grafana Security Posture panel shows hardening indexes for all 5 hosts

## Merge Criteria

- Workflow completes successfully with results from at least 3 hosts
- No CRITICAL CVEs in any running container image (if any are found, update the images before merging)
- Lynis hardening indexes are > 50 for all hosts
- Grafana panel deployed and showing data

## Notes For The Next Assistant

- Lynis runs as root; the Ansible task must use `become: yes`; the report file must be fetched as root and then chown'd to the automation user before the fetch module runs, or use `become_user: root` explicitly
- Trivy needs to pull image manifests from the registry (`registry.lv3.org`); ensure the build server has valid step-ca TLS certificates and the registry is reachable; if not, pass `--skip-db-update` and use a pre-cached DB
- Add `#platform-security` Mattermost channel before the workflow runs; ensure the Alertmanager Mattermost webhook has posting rights to this channel
- The hardening index trend comparison requires storing the previous week's report; read the most recent file in `receipts/security-reports/` and compare indexes; the first run has no baseline and should report `N/A (first run)` for the trend
