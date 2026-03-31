# Workstream ws-0279-live-apply: Live Apply ADR 0279 From Latest `origin/main`

- ADR: [ADR 0279](../adr/0279-grist-as-the-no-code-operational-spreadsheet-database.md)
- Title: Deploy Grist on `docker-runtime-lv3`, publish `grist.lv3.org`, and verify the OIDC-backed spreadsheet runtime end to end
- Status: live_applied
- Included In Repo Version: 0.177.113
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-31-adr-0279-grist-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.75
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0279-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0279-live-apply`
- Owner: codex
- Depends On: `adr-0063-keycloak-sso`, `adr-0086-backup-and-recovery`, `adr-0191-immutable-guest-replacement`, `adr-0279-grist-as-the-no-code-operational-spreadsheet-database`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0279-grist-as-the-no-code-operational-spreadsheet-database.md`, `docs/workstreams/ws-0279-live-apply.md`, `docs/runbooks/configure-grist.md`, `playbooks/grist.yml`, `playbooks/services/grist.yml`, `collections/ansible_collections/lv3/platform/roles/grist_runtime/`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `config/subdomain-catalog.json`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/secret-catalog.json`, `config/controller-local-secrets.json`, `config/image-catalog.json`, `config/api-gateway-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/service-completeness.json`, `config/grafana/dashboards/grist.json`, `config/alertmanager/rules/grist.yml`, `config/prometheus/file_sd/slo_targets.yml`, `config/prometheus/file_sd/https_tls_targets.yml`, `config/prometheus/rules/slo_rules.yml`, `config/prometheus/rules/slo_alerts.yml`, `config/prometheus/rules/https_tls_alerts.yml`, `config/uptime-kuma/monitors.json`, `config/subdomain-exposure-registry.json`, `receipts/image-scans/`, `receipts/live-applies/`, `workstreams.yaml`

## Purpose

Implement ADR 0279 by making Grist a repo-managed, OIDC-backed operational
spreadsheet runtime on `docker-runtime-lv3`, then preserve enough live proof
and branch-local state that the later exact-main integration replay can cut
the protected release-truth surfaces safely.

## Branch-Local Delivery

- The original workstream added the repo-managed Grist runtime, publication,
  monitoring, and backup-scope surfaces together with the supporting Keycloak
  and OpenBao integration required by ADR 0279.
- The synchronized branch-local replay also hardened the shared OpenBao
  compose-env helper so runtime secret injection can recover the local OpenBao
  API after shared Docker restarts.
- The March 31 latest-main integration replay on `codex/ws-0279-main-merge-r2`
  preserved the earlier Grist capability while adding the Grist persist
  ownership repair, pre-start Keycloak discovery gating, broader Keycloak
  startup recovery, mail-platform stale-network recovery, and the Docker
  bridge-chain recovery fix that surfaced only on the current merged baseline.

## Verification

- The first synchronized production proof remains preserved in
  `receipts/live-applies/2026-03-30-adr-0279-grist-live-apply.json`, and it
  records the first live platform version where Grist became true:
  `0.130.60`.
- The current authoritative latest-main proof uses repository version
  `0.177.113` on top of the synchronized `0.177.112 / 0.130.74` baseline and
  is preserved in
  `receipts/live-applies/2026-03-31-adr-0279-grist-mainline-live-apply.json`.
- The March 31 exact-main chronology is preserved in
  `receipts/live-applies/evidence/2026-03-31-adr-0279-grist-mainline-live-apply-0.177.113-r1.txt`,
  `...-r2.txt`, `...-r3.txt`, `...-r4.txt`, and the successful
  `...-r5.txt`.
- The focused repo-side validation and syntax proof is preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0279-mainline-validation-r1.txt`,
  which records the Grist playbook syntax check plus `54 passed` across the
  latest-main role regression slice.
- Fresh post-success proofs in
  `receipts/live-applies/evidence/2026-03-31-ws-0279-mainline-host-state-r1.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0279-mainline-runtime-state-r1.txt`,
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0279-mainline-public-probes-r1.txt`
  reconfirm `pve-manager/9.1.6` on kernel `6.17.13-2-pve`, the split static
  and secret Grist env files on `docker-runtime-lv3`, `/opt/grist/persist`
  owned by `1001:1001`, `https://grist.lv3.org/status` returning the canonical
  alive string, `https://grist.lv3.org/o/docs/` redirecting into the Keycloak
  auth flow, and live Keycloak discovery at
  `https://sso.lv3.org/realms/lv3/.well-known/openid-configuration`.

## Outcome

- ADR 0279 first became true on integrated repo version `0.177.105` and
  platform version `0.130.60`.
- The current authoritative latest-main replay is now release `0.177.113` on
  platform version `0.130.75`.
- `receipts/live-applies/2026-03-31-adr-0279-grist-mainline-live-apply.json`
  supersedes the earlier March 30 mainline receipt as the canonical proof for
  `grist` while preserving both the first branch-local receipt and the March 30
  mainline replay in the audit trail.
