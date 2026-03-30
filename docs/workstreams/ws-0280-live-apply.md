# Workstream ws-0280-live-apply: ADR 0280 Live Apply From Latest `origin/main`

- ADR: [ADR 0280](../adr/0280-changedetection-io-for-external-content-and-api-change-monitoring.md)
- Title: private Changedetection.io external content and API change monitoring live apply
- Status: in_progress
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
- `playbooks/changedetection.yml`
- `playbooks/services/changedetection.yml`
- `collections/ansible_collections/lv3/platform/roles/changedetection_runtime/`
- `scripts/changedetection_sync.py`
- `tests/test_changedetection_runtime_role.py`
- `tests/test_changedetection_metadata.py`
- `tests/test_changedetection_sync.py`
- `tests/test_generate_platform_vars.py`
- `receipts/image-scans/2026-03-30-changedetection-runtime.json`
- `receipts/image-scans/2026-03-30-changedetection-runtime.trivy.json`
- `receipts/live-applies/`
- `docs/adr/.index.yaml`

## Verification

- repository validation completed on the branch before the live apply pause:
  - `uv run --with pytest --with pyyaml pytest tests/test_changedetection_runtime_role.py tests/test_changedetection_metadata.py tests/test_changedetection_sync.py tests/test_generate_platform_vars.py -q`
  - `make syntax-check-changedetection`
  - `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
  - `uvx --from pyyaml python scripts/interface_contracts.py --check-live-apply service:changedetection`
  - `./scripts/validate_repo.sh agent-standards`
- direct guest checks confirmed `docker-runtime-lv3` did not have Changedetection live before this workstream:
  - `/opt/changedetection/docker-compose.yml` absent
  - TCP `5000` absent
  - `/etc/lv3/changedetection/api-token` absent
- first live apply evidence was recorded in `receipts/live-applies/evidence/2026-03-30-ws-0280-converge-changedetection.txt`
- the initial converge stopped while resolving Mattermost notification routing because the live Mattermost webhook manifest on `docker-runtime-lv3` does not currently include the repo-declared `platform-ops` / `ops` webhook key required by ADR 0280

## Remaining For Merge-To-Main

- exact-main integration still needs the protected release and canonical-truth surfaces once branch-local live apply is verified
- if the live apply succeeds on this branch, the final merge-to-main step still needs to refresh `VERSION`, `changelog.md`, `versions/stack.yaml`, and generated canonical-truth surfaces from exact `origin/main`
