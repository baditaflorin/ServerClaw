# Workstream ws-0279-main-merge

- ADR: [ADR 0279](../adr/0279-grist-as-the-no-code-operational-spreadsheet-database.md)
- Title: Integrate ADR 0279 Grist exact-main replay onto `origin/main`
- Status: in_progress
- Included In Repo Version: 0.177.113
- Platform Version Observed During Integration: 0.130.75
- Release Date: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0279-main-publish-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0279-main-publish-r1`
- Owner: codex
- Depends On: `ws-0279-live-apply`

## Purpose

Carry the verified ADR 0279 Grist work onto the newest merged `origin/main`,
rerun the exact-main live apply from the synchronized baseline, refresh the
protected release and canonical-truth surfaces from that result, and publish
the now-hardened Grist runtime plus its login-gated public surface on `main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0279-main-merge.md`
- `docs/workstreams/ws-0279-live-apply.md`
- `docs/adr/0279-grist-as-the-no-code-operational-spreadsheet-database.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-grist.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `playbooks/grist.yml`
- `playbooks/services/grist.yml`
- `collections/ansible_collections/lv3/platform/roles/grist_runtime/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_compose_env.yml`
- `config/ansible-execution-scopes.yaml`
- `config/subdomain-catalog.json`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/image-catalog.json`
- `config/certificate-catalog.json`
- `config/api-gateway-catalog.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/grafana/dashboards/grist.json`
- `config/grafana/dashboards/slo-overview.json`
- `config/alertmanager/rules/grist.yml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `config/uptime-kuma/monitors.json`
- `config/subdomain-exposure-registry.json`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `receipts/ops-portal-snapshot.html`
- `receipts/image-scans/2026-03-30-grist-runtime.json`
- `receipts/image-scans/2026-03-30-grist-runtime.trivy.json`
- `receipts/live-applies/2026-03-30-adr-0279-grist-live-apply.json`
- `receipts/live-applies/2026-03-30-adr-0279-grist-mainline-live-apply.json`
- `receipts/live-applies/2026-03-31-adr-0279-grist-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-adr-0279-*`
- `receipts/live-applies/evidence/2026-03-31-adr-0279-*`
- `receipts/live-applies/evidence/2026-03-31-ws-0279-mainline-*`

## Verification

- `git fetch origin --prune` confirmed the latest shared `origin/main`
  baseline is commit `58dad5d37ae16ceb3a73bc2fe4554b2a449e8f83`, which already
  carried release `0.177.112` and platform version `0.130.74`.
- ADR 0279 was then replayed onto that newer baseline in
  `codex/ws-0279-main-merge-r2`, preserving the earlier Grist capability while
  adding the Grist persist-ownership repair, pre-start Keycloak discovery gate,
  broader Keycloak startup recovery, mail-platform stale-network recovery, and
  the Docker bridge-chain repair surfaced only on the newer shared baseline.
- The focused latest-main compatibility slice returned `54 passed` across
  `tests/test_keycloak_runtime_role.py`, `tests/test_grist_runtime_role.py`,
  `tests/test_grist_playbook.py`, `tests/test_openbao_compose_env_helper.py`,
  `tests/test_common_docker_bridge_chains_helper.py`,
  `tests/test_mail_platform_runtime_role.py`, and
  `tests/test_docker_runtime_role.py`, with the Grist playbook syntax check and
  test output preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0279-mainline-validation-r1.txt`.
- The March 31 latest-main chronology is preserved in
  `receipts/live-applies/evidence/2026-03-31-adr-0279-grist-mainline-live-apply-0.177.113-r1.txt`,
  `...-r2.txt`, `...-r3.txt`, `...-r4.txt`, and the successful
  `...-r5.txt`.
- That chronology records the initial pre-hardening replay attempts, the
  restored public publication, the missing local login path, the Keycloak
  bootstrap fragility during shared Docker-network churn, and the final
  successful retry after the Grist plus Keycloak runtime hardening landed.
- The successful governed replay in
  `receipts/live-applies/evidence/2026-03-31-adr-0279-grist-mainline-live-apply-0.177.113-r5.txt`
  ended with final recap
  `docker-runtime-lv3 : ok=283 changed=2 unreachable=0 failed=0 skipped=98`,
  `nginx-lv3 : ok=46 changed=5 unreachable=0 failed=0 skipped=7`, and
  `localhost : ok=24 changed=0 unreachable=0 failed=0 skipped=6`.
- Fresh post-success proofs in
  `receipts/live-applies/evidence/2026-03-31-ws-0279-mainline-host-state-r1.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0279-mainline-runtime-state-r1.txt`,
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0279-mainline-public-probes-r1.txt`
  reconfirm `Debian-trixie-latest-amd64-base`,
  `pve-manager/9.1.6/71482d1833ded40a`, kernel `6.17.13-2-pve`, the split
  Grist static and runtime-secret env files, `/opt/grist/persist` owned by
  `1001:1001`, `https://grist.lv3.org/status` returning the canonical alive
  string, `https://grist.lv3.org/o/docs/` redirecting into Keycloak, and the
  live Keycloak discovery issuer still resolving to
  `https://sso.lv3.org/realms/lv3`.
- `receipts/live-applies/2026-03-31-adr-0279-grist-mainline-live-apply.json`
  now records the canonical latest-main receipt for ADR 0279, while the March
  30 mainline receipt and the earlier branch-local receipt remain preserved as
  audit history.

## Outcome

- Release `0.177.113` now carries ADR 0279 onto the latest shared mainline
  baseline of `0.177.112 / 0.130.74`.
- The March 31 latest-main replay refreshed the Grist runtime and login-gated
  public surface, re-verified the split static-plus-secret OIDC env model plus
  the new persist-ownership contract, and advances the tracked integrated
  platform baseline to `0.130.75`.
- `receipts/live-applies/2026-03-31-adr-0279-grist-mainline-live-apply.json`
  is now the canonical mainline receipt for ADR 0279; the earlier branch-local
  receipt on `0.130.60` and the March 30 mainline replay remain part of the
  audit trail.
