# Workstream ws-0249-live-apply: ADR 0249 Live Apply From Latest `origin/main`

- ADR: [ADR 0249](../adr/0249-https-and-tls-assurance-via-blackbox-exporter-and-testssl-sh.md)
- Title: live apply HTTPS and TLS assurance through Prometheus blackbox probes and periodic `testssl.sh` scans
- Status: live_applied
- Implemented In Repo Version: 0.177.54
- Live Applied In Platform Version: 0.130.43
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0249-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0249-live-apply`
- Owner: codex
- Depends On: `adr-0096-slo-tracking`, `adr-0101-certificate-lifecycle`, `adr-0142-public-surface-security-scan`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0249-live-apply.md`, `docs/adr/0249-https-and-tls-assurance-via-blackbox-exporter-and-testssl-sh.md`, `docs/adr/.index.yaml`, `docs/runbooks/https-tls-assurance.md`, `docs/runbooks/monitoring-stack.md`, `config/prometheus/file_sd/https_tls_targets.yml`, `config/prometheus/rules/https_tls_alerts.yml`, `config/workflow-catalog.json`, `config/windmill/scripts/https-tls-assurance.py`, `scripts/https_tls_assurance_targets.py`, `scripts/generate_https_tls_assurance.py`, `scripts/https_tls_assurance.py`, `scripts/public_surface_scan.py`, `collections/ansible_collections/lv3/platform/roles/monitoring_vm/`, `tests/test_https_tls_assurance_targets.py`, `tests/test_monitoring_vm_role.py`, `receipts/https-tls-assurance/`, `receipts/live-applies/`

## Scope

- derive the ADR 0249 HTTPS surface set from the service, subdomain,
  certificate, and health-probe catalogs
- generate Prometheus blackbox targets and expiry/failure alert rules for that
  surface set
- replay the monitoring stack from this isolated worktree and verify the new
  blackbox job plus Prometheus rule group on `monitoring-lv3`
- run the deeper `testssl.sh` assurance path, store a receipt, and capture the
  final live-apply evidence for safe merge-to-`main` integration

## Verification

- `python3 -m py_compile scripts/https_tls_assurance.py config/windmill/scripts/https-tls-assurance.py`
- `uv run --with pytest --with pyyaml pytest -q tests/test_https_tls_assurance_windmill_wrapper.py tests/test_https_tls_assurance_targets.py tests/test_monitoring_vm_role.py tests/test_guest_observability_role.py tests/test_guest_log_shipping_playbook.py tests/test_loki_log_agent_role.py` returned `19 passed in 0.36s`
- `make validate-generated-https-tls-assurance`
- `make syntax-check-monitoring`
- `./scripts/validate_repo.sh alert-rules agent-standards`
- `make preflight WORKFLOW=converge-monitoring`
- `make converge-monitoring`
- SSH verification on `monitoring-lv3` confirmed the Prometheus HTTPS/TLS targets file, alert rules file, active monitoring services, 31 active `https-tls-blackbox` targets, and 93 loaded `https_tls_assurance` rules
- `make https-tls-assurance ENV=production` recorded branch-local receipts for both the accepted 60-second timeout budget and the rejected 120-second experiment

## Notes For The Next Assistant

- The branch-local live apply is complete and recorded in `receipts/live-applies/2026-03-28-adr-0249-https-tls-assurance-live-apply.json`.
- The protected integration files still need to wait for the final merge-to-main step on the latest `origin/main`.
- The 2026-03-28 timeout comparison showed that raising `testssl.sh` from 60 seconds to 120 seconds increased timeout findings from 16 to 26 surfaces and nearly doubled total runtime, so this branch intentionally keeps the 60-second default.
