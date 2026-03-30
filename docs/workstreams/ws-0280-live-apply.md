# Workstream ws-0280-live-apply: ADR 0280 Live Apply From Latest `origin/main`

- ADR: [ADR 0280](../adr/0280-changedetection-io-for-external-content-and-api-change-monitoring.md)
- Title: private Changedetection.io external content and API change monitoring live apply
- Status: ready_for_merge
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

- targeted validation on the repaired workstream branch passed before the final replay:
  - `uv run --with pytest --with pyyaml pytest tests/test_changedetection_sync.py tests/test_changedetection_runtime_role.py tests/test_changedetection_metadata.py tests/test_generate_platform_vars.py -q` returned `41 passed in 1.59s`
  - `make syntax-check-changedetection`
  - `make syntax-check-mattermost`
  - `make syntax-check-netbox`
- direct guest checks confirmed `docker-runtime-lv3` did not have Changedetection live before this workstream:
  - `/opt/changedetection/docker-compose.yml` absent
  - TCP `5000` absent
  - `/etc/lv3/changedetection/api-token` absent
- the first live converge exposed a Mattermost dependency gap instead of a Changedetection runtime bug:
  - `receipts/live-applies/evidence/2026-03-30-ws-0280-converge-mattermost-unblock-r1.txt` captured the invalid retention configuration that kept Mattermost crash-looping
  - `receipts/live-applies/evidence/2026-03-30-ws-0280-converge-mattermost-unblock-r3.txt` captured the repaired Mattermost replay after fixing retention defaults and guest-side PostgreSQL host resolution
- the Changedetection correction loop is preserved in the sequential branch evidence:
  - `receipts/live-applies/evidence/2026-03-30-ws-0280-converge-changedetection-r2.txt` through `receipts/live-applies/evidence/2026-03-30-ws-0280-converge-changedetection-r8.txt`
  - the final authoritative replay is `receipts/live-applies/evidence/2026-03-30-ws-0280-converge-changedetection-r8.txt`, which completed with `docker-runtime-lv3 : ok=311 changed=118 unreachable=0 failed=0 skipped=33 rescued=0 ignored=0`
- direct settled-state proofs after the successful replay are recorded in:
  - `receipts/live-applies/evidence/2026-03-30-ws-0280-host-state-r2.txt`
  - `receipts/live-applies/evidence/2026-03-30-ws-0280-changedetection-runtime-state-r1.txt`
  - `receipts/live-applies/evidence/2026-03-30-ws-0280-changedetection-health-r1.txt`
  - `receipts/live-applies/evidence/2026-03-30-ws-0280-changedetection-gateway-route-r1.txt`

## Remaining For Merge-To-Main

- `origin/main` advanced during the branch-local replay, so the exact-main integration still needs a fresh rebase before merge
- the exact-main step still needs to refresh the protected release and canonical-truth surfaces from the latest `origin/main`
- the final integration step on `main` must update `VERSION`, `changelog.md`, `versions/stack.yaml`, the integrated `README.md` status summary, and ADR 0280's final repo/platform implementation metadata after the exact-main replay succeeds
