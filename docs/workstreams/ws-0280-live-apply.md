# Workstream ws-0280-live-apply: ADR 0280 Live Apply From Latest `origin/main`

- ADR: [ADR 0280](../adr/0280-changedetection-io-for-external-content-and-api-change-monitoring.md)
- Title: private Changedetection.io external content and API change monitoring live apply
- Status: live_applied
- Included In Repo Version: 0.177.100
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0280-changedetection-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0280-changedetection-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.63
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0280-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0280-live-apply`
- Owner: codex
- Depends On: `adr-0086-backup-and-recovery-for-stateful-services`, `adr-0092-unified-platform-api-gateway`, `adr-0124-ntfy-for-lightweight-push-notifications`
- Conflicts With: none

## Scope

- add the repo-managed private Changedetection.io runtime, watch catalogue, notification routing, and authenticated `/v1/changedetection` API gateway route
- wire the service into the platform inventory, catalog, SLO, health probe, redundancy, workflow, and command surfaces so repository automation can validate and replay it safely
- live-apply the service from an isolated latest-main worktree, verify the private runtime and gateway contract end to end, and leave merge-safe receipts plus ADR metadata behind

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0280-live-apply.md`
- `docs/adr/0280-changedetection-io-for-external-content-and-api-change-monitoring.md`
- `docs/runbooks/configure-changedetection.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `Makefile`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/api-gateway-catalog.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/grafana/dashboards/slo-overview.json`
- `docs/site-generated/architecture/dependency-graph.md`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/diagrams/trust-tier-model.excalidraw`
- `collections/ansible_collections/lv3/platform/roles/mattermost_runtime/templates/mattermost.env.j2`
- `collections/ansible_collections/lv3/platform/roles/mattermost_runtime/templates/mattermost.env.ctmpl.j2`
- `playbooks/changedetection.yml`
- `playbooks/services/changedetection.yml`
- `collections/ansible_collections/lv3/platform/roles/changedetection_runtime/`
- `scripts/changedetection_sync.py`
- `tests/test_changedetection_runtime_role.py`
- `tests/test_changedetection_metadata.py`
- `tests/test_changedetection_sync.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_data_retention_role.py`
- `receipts/image-scans/2026-03-30-changedetection-runtime.json`
- `receipts/image-scans/2026-03-30-changedetection-runtime.trivy.json`
- `receipts/live-applies/`
- `docs/adr/.index.yaml`

## Verification

- The branch-local live apply first made ADR 0280 true on platform version
  `0.130.63`, recorded in
  `receipts/live-applies/2026-03-30-adr-0280-changedetection-live-apply.json`.
- The first live converge exposed shared dependency gaps rather than a
  Changedetection runtime design bug:
  `receipts/live-applies/evidence/2026-03-30-ws-0280-converge-mattermost-unblock-r1.txt`
  captured the invalid Mattermost retention combination, and
  `receipts/live-applies/evidence/2026-03-30-ws-0280-converge-mattermost-unblock-r3.txt`
  captured the repaired replay after the retention and guest-side PostgreSQL
  fixes landed.
- The Changedetection correction loop is preserved in the sequential branch
  evidence from
  `receipts/live-applies/evidence/2026-03-30-ws-0280-converge-changedetection-r2.txt`
  through
  `receipts/live-applies/evidence/2026-03-30-ws-0280-converge-changedetection-r8.txt`;
  the settled branch-local replay completed with
  `docker-runtime-lv3 : ok=311 changed=118 unreachable=0 failed=0 skipped=33 rescued=0 ignored=0`.
- The exact-main retry branch then rebased ADR 0280 onto the shared
  `0.177.99 / 0.130.66` baseline, where the focused compatibility slice passed
  with `64 passed in 2.57s` in
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r2-targeted-checks-r1.txt`,
  the syntax sweep passed in
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r2-syntax-checks-r1.txt`,
  and the protected release write prepared `0.177.100` in
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r2-release-write-r1.txt`.
- The canonical committed-source replay from
  `65305c70c7049bcb177f59b5a44ab0d031a8a10c` succeeded in
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-live-apply-0.177.100.txt`
  with final recap
  `docker-runtime-lv3 : ok=312 changed=115 unreachable=0 failed=0 skipped=32 rescued=0 ignored=0`.
- Fresh current-server proofs from that committed replay are preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-host-state-r1-0.177.100.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-changedetection-runtime-state-r1-0.177.100.txt`,
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-gateway-route-r1-0.177.100.html`,
  confirming Debian 13 / Proxmox VE 9.1.6 on the host, a healthy
  Changedetection `0.54.7` runtime with `9` watches and `4` tags on
  `docker-runtime-lv3`, a drift-free sync report, and a live authenticated
  `/v1/changedetection` gateway route.

## Remaining For Merge-To-Main

- The branch-local receipt remains the first-live audit trail for ADR 0280 on
  platform version `0.130.63`.
- The protected release and canonical-truth surfaces are now carried by
  `ws-0280-main-merge`, whose canonical receipt is
  `receipts/live-applies/2026-03-30-adr-0280-changedetection-mainline-live-apply.json`.
- The exact-main integration lane advances the tracked platform baseline from
  `0.130.66` to `0.130.67` on release `0.177.100` while preserving this
  workstream's branch-local evidence as audit history.
