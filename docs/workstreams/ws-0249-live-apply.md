# Workstream ws-0249-live-apply: ADR 0249 Live Apply From Latest `origin/main`

- ADR: [ADR 0249](../adr/0249-https-and-tls-assurance-via-blackbox-exporter-and-testssl-sh.md)
- Title: live apply HTTPS and TLS assurance through Prometheus blackbox probes and periodic `testssl.sh` scans
- Status: live_applied
- Implemented In Repo Version: 0.177.82
- Live Applied In Platform Version: 0.130.56
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
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

- `python3 -m py_compile scripts/https_tls_assurance_targets.py scripts/generate_https_tls_assurance.py scripts/https_tls_assurance.py config/windmill/scripts/https-tls-assurance.py`
- `uv run --with pytest --with pyyaml pytest -q tests/test_https_tls_assurance_targets.py tests/test_https_tls_assurance_windmill_wrapper.py tests/test_monitoring_vm_role.py tests/test_guest_observability_role.py tests/test_guest_log_shipping_playbook.py tests/test_loki_log_agent_role.py` returned `22 passed in 0.50s`
- `make validate-generated-https-tls-assurance`
- `make syntax-check-monitoring`
- `./scripts/validate_repo.sh alert-rules agent-standards`
- `make preflight WORKFLOW=converge-monitoring`
- `make converge-monitoring`
- SSH verification on `proxmox_florin` and `monitoring-lv3` confirmed kernel `6.17.13-2-pve`, `pve-manager/9.1.6`, active monitoring services, the Prometheus HTTPS/TLS targets file, the alert rules file, 33 active `https-tls-blackbox` targets, and 99 loaded `https_tls_assurance` rules
- `uv run --with pyyaml python scripts/https_tls_assurance.py --env production --skip-testssl --print-report-json` recorded clean discovery receipt `20260329T151822Z` with `33` discovered targets
- `make https-tls-assurance ENV=production` recorded receipt `20260329T151359Z` with `33` targets in `677.4` seconds, status `warn`, `11` medium `tls.scan_timeout` findings, and no high or critical findings

## Notes For The Next Assistant

- The canonical merge-to-main receipt is `receipts/live-applies/2026-03-29-adr-0249-https-tls-assurance-mainline-live-apply.json`; the older 2026-03-28 branch-local receipt remains as historical comparison evidence.
- While ADR 0249 was being integrated, `origin/main` advanced through the ADR 0236 exact-main replay and release `0.177.81` / platform `0.130.55`; after rebasing onto that current mainline, a refreshed live server check still reported the same ADR 0249 monitoring state with 33 active HTTPS/TLS targets and 99 rules, so no second monitoring replay was required before merge.
- The 2026-03-29 60-second production replay completed faster and with fewer timeouts than the earlier 2026-03-28 comparison baseline, so this branch keeps the 60-second default.
