# Workstream ws-0249-live-apply: ADR 0249 Live Apply From Latest `origin/main`

- ADR: [ADR 0249](../adr/0249-https-and-tls-assurance-via-blackbox-exporter-and-testssl-sh.md)
- Title: live apply HTTPS and TLS assurance through Prometheus blackbox probes and periodic `testssl.sh` scans
- Status: in-progress
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

- pending live replay

## Notes For The Next Assistant

- The branch-local implementation is in progress from the latest `origin/main`
  worktree created on `2026-03-28`.
- The protected integration files still need to wait for the final merge-to-main
  step after the live replay is verified.
