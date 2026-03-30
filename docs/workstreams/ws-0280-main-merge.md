# Workstream ws-0280-main-merge

- ADR: [ADR 0280](../adr/0280-changedetection-io-for-external-content-and-api-change-monitoring.md)
- Title: Integrate ADR 0280 Changedetection exact-main replay onto `origin/main`
- Status: in_progress
- Included In Repo Version: pending
- Platform Version Observed During Integration: 0.130.64
- Release Date: pending
- Live Applied On: pending
- Branch: `codex/ws-0280-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0280-main-merge`
- Owner: codex
- Depends On: `ws-0280-live-apply`

## Purpose

Carry the verified ADR 0280 Changedetection workstream onto the newest
available `origin/main`, rerun the exact-main replay from committed source on
that synchronized baseline, refresh the protected release and canonical-truth
surfaces from the resulting tree, and publish the private Changedetection
runtime plus its authenticated `/v1/changedetection` gateway contract on
`main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0280-main-merge.md`
- `docs/workstreams/ws-0280-live-apply.md`
- `docs/adr/0280-changedetection-io-for-external-content-and-api-change-monitoring.md`
- `docs/adr/.index.yaml`
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
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/diagrams/trust-tier-model.excalidraw`
- `collections/ansible_collections/lv3/platform/roles/mattermost_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/mattermost_runtime/templates/mattermost.env.j2`
- `collections/ansible_collections/lv3/platform/roles/mattermost_runtime/templates/mattermost.env.ctmpl.j2`
- `collections/ansible_collections/lv3/platform/roles/netbox_runtime/defaults/main.yml`
- `playbooks/changedetection.yml`
- `playbooks/services/changedetection.yml`
- `collections/ansible_collections/lv3/platform/roles/changedetection_runtime/`
- `scripts/changedetection_sync.py`
- `tests/test_changedetection_runtime_role.py`
- `tests/test_changedetection_metadata.py`
- `tests/test_changedetection_sync.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_data_retention_role.py`
- `tests/test_openbao_runtime_role.py`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `receipts/image-scans/2026-03-30-changedetection-runtime.json`
- `receipts/image-scans/2026-03-30-changedetection-runtime.trivy.json`
- `receipts/live-applies/2026-03-30-adr-0280-changedetection-live-apply.json`
- `receipts/live-applies/2026-03-30-adr-0280-changedetection-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-*`

## Verification

- exact-main replay pending from the current `origin/main` baseline
- protected release and canonical-truth surfaces pending until the replay,
  current-server probes, and repository automation all succeed on this branch

## Outcome

- pending exact-main replay, final release bump, and `origin/main` push
