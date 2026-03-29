# Workstream ws-0278-live-apply: ADR 0278 Live Apply From Latest `origin/main`

- ADR: [ADR 0278](../adr/0278-gotenberg-as-the-document-to-pdf-rendering-service.md)
- Title: private Gotenberg document-to-PDF rendering service live apply
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0278-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0278-live-apply`
- Owner: codex
- Depends On: `adr-0092-unified-platform-api-gateway`, `adr-0151-n8n-as-the-external-app-connector-fabric`, `adr-0199-outline-living-knowledge-wiki`, `adr-0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3`, `adr-0274-minio-as-the-s3-compatible-object-storage-layer`, `adr-0275-apache-tika-server-for-document-text-extraction-in-the-rag-pipeline`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0278-live-apply.md`, `docs/adr/0278-gotenberg-as-the-document-to-pdf-rendering-service.md`, `docs/runbooks/configure-gotenberg.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `Makefile`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/image-catalog.json`, `config/service-completeness.json`, `config/api-gateway-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/command-catalog.json`, `config/workflow-catalog.json`, `config/grafana/dashboards/gotenberg.json`, `config/alertmanager/rules/gotenberg.yml`, `playbooks/gotenberg.yml`, `playbooks/services/gotenberg.yml`, `collections/ansible_collections/lv3/platform/roles/gotenberg_runtime/`, `tests/test_gotenberg_runtime_role.py`, `receipts/image-scans/`, `receipts/live-applies/`, `docs/adr/.index.yaml`

## Scope

- add the repo-managed private Gotenberg runtime, firewall exposure, health probes, dashboard, alerting, SLO, and data-catalog surfaces
- refresh the shared API gateway so authenticated callers can use `/v1/gotenberg` without publishing a dedicated public hostname
- live-apply the service from an isolated latest-main worktree, verify Chromium and LibreOffice render paths end to end, and leave merge-safe receipts plus ADR metadata behind

## Verification

- pending

## Live Evidence

- pending

## Remaining For Mainline Integration

- protected integration files (`VERSION`, `changelog.md`, `README.md`, and `versions/stack.yaml`) intentionally remain untouched on this workstream branch until the final verified integration step on `main`
