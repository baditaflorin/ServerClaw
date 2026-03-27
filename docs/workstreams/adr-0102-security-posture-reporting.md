# Workstream ADR 0102: Security Posture Reporting and Benchmark Drift

- ADR: [ADR 0102](../adr/0102-security-posture-reporting.md)
- Title: Weekly Lynis host hardening scans and Trivy container image CVE scans with results in the ops portal, GlitchTip, and Mattermost
- Status: merged
- Branch: `codex/adr-0102-security-posture`
- Worktree: `../proxmox_florin_server-security-posture`
- Owner: codex
- Depends On: `adr-0006-security-baseline`, `adr-0024-docker-security`, `adr-0044-windmill`, `adr-0057-mattermost`, `adr-0061-glitchtip`, `adr-0066-audit-log`, `adr-0068-image-policy`, `adr-0087-validation-gate`, `adr-0093-interactive-ops-portal`, `adr-0097-alerting-routing`
- Conflicts With: none
- Shared Surfaces: `playbooks/tasks/`, `scripts/`, `config/workflow-catalog.json`, `config/control-plane-lanes.json`, `config/api-publication.json`, Grafana dashboard templates, `receipts/`

## Scope

- write `playbooks/tasks/security-scan.yml` — Ansible playbook that runs Lynis on target hosts and fetches reports
- write `scripts/parse_lynis_report.py` — parses Lynis `.dat` report into structured JSON
- write `scripts/trivy_scan_running_images.sh` — scans the running images on each Docker host via the containerized Trivy runner
- write `scripts/security_posture_report.py` — aggregates Lynis and Trivy results into a unified report JSON
- write Windmill workflow `security-posture-scan` — scheduled Monday 01:00 UTC; orchestrates all scans
- write `config/lynis-suppressions.json` — known-acceptable Lynis findings to suppress from reporting
- add `receipts/security-reports/.gitkeep`
- add Security Posture sections to the generated ops portal and the managed platform overview dashboard template
- add `platform.security.*` event-lane registration and publication metadata
- make the workflow optionally forward summaries to Mattermost, critical findings to GlitchTip, and metrics to InfluxDB

## Non-Goals

- Automated remediation of Lynis findings
- MEDIUM/LOW CVE reporting from Trivy (HIGH/CRITICAL only)
- Compliance reporting against specific frameworks (SOC2, ISO 27001) in this iteration

## Expected Repo Surfaces

- `playbooks/tasks/security-scan.yml`
- `scripts/parse_lynis_report.py`
- `scripts/trivy_scan_running_images.sh`
- `scripts/security_posture_report.py`
- `config/windmill/scripts/security-posture-scan.py`
- `config/workflow-catalog.json`
- `config/control-plane-lanes.json`
- `config/api-publication.json`
- `config/lynis-suppressions.json`
- `receipts/security-reports/.gitkeep`
- `collections/ansible_collections/lv3/platform/roles/monitoring_vm/templates/lv3-platform-overview.json.j2`
- `scripts/generate_ops_portal.py`
- `docs/runbooks/security-posture-reporting.md`
- `docs/adr/0102-security-posture-reporting.md`
- `docs/workstreams/adr-0102-security-posture-reporting.md`

## Expected Live Surfaces

- Windmill `security-posture-scan` workflow has at least one successful run from the worker checkout
- `receipts/security-reports/` contains at least one report JSON
- Grafana platform overview shows Security Posture panels backed by the repo-managed line protocol metrics
- NATS `platform.security.*` is receivable when publication is enabled

## Verification

- `python3 -m py_compile scripts/parse_lynis_report.py scripts/security_posture_report.py config/windmill/scripts/security-posture-scan.py`
- `python3 scripts/parse_lynis_report.py tests/fixtures/security_posture_docker_runtime.dat`
- `uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_parse_lynis_report.py tests/test_security_posture_report.py tests/test_ops_portal.py`
- `uv run --with pyyaml --with jsonschema python scripts/generate_ops_portal.py --check`

## Merge Criteria

- repo workflow surfaces validate and the targeted tests pass
- the report generator writes a receipt, compares to the previous receipt, and emits the expected summary shape
- the ops portal and dashboard templates include the security posture summary surfaces
- the ADR, runbook, and workstream registry reflect repository implementation status

## Notes For The Next Assistant

- The current repo implementation is intentionally receipt-first; no live platform version bump is claimed until the workflow is scheduled from `main` and a successful live receipt exists.
- The containerized Trivy runner uses the host Docker socket, so it can scan the currently running images without a separate native Trivy install.
- The hardening index trend comparison reads the newest existing receipt in `receipts/security-reports/`; the first run has no baseline and therefore no delta.

## Outcome

- repository implementation is complete on `main` in repo release `0.109.0`
- the branch now adds worker-portable SSH handling for the security scan workflow, a stale-Lynis-lock cleanup task, and a cached-Lynis retry path for report aggregation
- the first verified production receipt is committed at `receipts/security-reports/20260326T140237Z.json` with summary totals `critical=126`, `high=1300`, and `lowest_hardening_index=62`
- a full worker-side replay from `windmill-windmill_worker-1` is now also committed at `receipts/security-reports/20260326T170143Z.json`, confirming the mirrored checkout can execute the complete Lynis plus Trivy path through the private Proxmox jump
- the branch-local live-apply record is committed at `receipts/live-applies/2026-03-26-adr-0102-security-posture-live-apply.json`
- focused validation passed with `python3 -m py_compile scripts/parse_lynis_report.py scripts/security_posture_report.py config/windmill/scripts/security-posture-scan.py`, `uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_parse_lynis_report.py tests/test_security_posture_report.py tests/test_ops_portal.py`, `uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_security_posture_report.py tests/test_security_posture_windmill_wrapper.py`, `uv run --with pyyaml --with jsonschema python scripts/generate_ops_portal.py --check`, `make validate-generated-portals`, and `make syntax-check-windmill`
- a full `ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --limit docker-runtime-lv3 ...` replay now completes cleanly after the bytecode-purge fix, confirming the Windmill runtime role can refresh the worker checkout and seed state without the earlier API disconnect
- the worker wrapper returns a structured `status: ok` payload and writes the new receipt above; the wrapped report command surfaces `returncode=1` only because the generated security summary status is `critical`
