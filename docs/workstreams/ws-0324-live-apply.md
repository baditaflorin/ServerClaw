# Workstream ws-0324-live-apply: Live Apply ADR 0324 From Latest `origin/main`

- ADR: [ADR 0324](../adr/0324-service-definition-shards-and-generated-service-catalog-assembly.md)
- Title: Implement ADR 0324 by moving service metadata into per-service bundles and verifying the generated-catalog automation end to end
- Status: in_progress
- Branch: `codex/ws-0324-live-apply`
- Worktree: `.worktrees/ws-0324-live-apply`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0107-platform-extension-model`, `adr-0174-integration-only-canonical-truth-assembly`, `adr-0179-service-redundancy-tier-matrix`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0324-live-apply.md`, `docs/adr/0324-service-definition-shards-and-generated-service-catalog-assembly.md`, `docs/adr/.index.yaml`, `.repo-structure.yaml`, `.config-locations.yaml`, `catalog/services/`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/service-completeness.json`, `config/service-redundancy-catalog.json`, `config/dependency-graph.json`, `config/data-catalog.json`, `config/slo-catalog.json`, `config/prometheus/rules/slo_rules.yml`, `config/prometheus/rules/slo_alerts.yml`, `config/prometheus/file_sd/slo_targets.yml`, `config/grafana/dashboards/slo-overview.json`, `docs/schema/service-definition-*.json`, `docs/schema/health-probe-catalog.schema.json`, `docs/runbooks/service-capability-catalog.md`, `docs/runbooks/add-a-new-service.md`, `docs/runbooks/scaffold-new-service.md`, `.yamllint`, `Makefile`, `scripts/service_definition_catalog.py`, `scripts/service_catalog.py`, `scripts/scaffold_service.py`, `scripts/validate_repo.sh`, `tests/test_service_definition_catalog.py`, `tests/test_scaffold_service.py`, `tests/test_validate_service_catalog.py`, `docs/diagrams/agent-coordination-map.excalidraw`, `receipts/live-applies/*0324*`, `receipts/live-applies/evidence/2026-04-03-ws-0324-*`, `README.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`

## Scope

- create a `catalog/services/<service-id>/` source tree that makes service-local metadata the ADR 0324 source of truth
- generate the existing aggregate service catalogs from those bundles so downstream callers and docs keep working unchanged
- switch validation and service scaffolding onto the new bundle workflow
- replay the repo automation on the branch, then on the synchronized live worker and mainline validation paths

## Non-Goals

- changing the declared runtime topology or adding new product surfaces beyond the catalog-source refactor itself
- claiming protected release, README, or `versions/stack.yaml` truth before the final exact-main integration step
- migrating unrelated ADR 0325 through ADR 0328 generator work into this ADR 0324 live apply

## Expected Repo Surfaces

- `catalog/services/_metadata.yaml`
- `catalog/services/<service-id>/service.yaml`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/dependency-graph.json`
- `config/data-catalog.json`
- `config/slo-catalog.json`
- `config/prometheus/rules/slo_rules.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/grafana/dashboards/slo-overview.json`
- `docs/schema/service-definition-*.json`
- `docs/schema/health-probe-catalog.schema.json`
- `scripts/service_definition_catalog.py`
- `scripts/service_catalog.py`
- `scripts/scaffold_service.py`
- `scripts/validate_repo.sh`
- `Makefile`
- `.repo-structure.yaml`
- `.config-locations.yaml`
- `docs/runbooks/service-capability-catalog.md`
- `docs/runbooks/add-a-new-service.md`
- `docs/runbooks/scaffold-new-service.md`
- `.yamllint`
- `docs/adr/0324-service-definition-shards-and-generated-service-catalog-assembly.md`
- `docs/workstreams/ws-0324-live-apply.md`
- `tests/test_service_definition_catalog.py`
- `tests/test_scaffold_service.py`
- `tests/test_validate_service_catalog.py`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `receipts/live-applies/*0324*`
- `receipts/live-applies/evidence/2026-04-03-ws-0324-*`

## Expected Live Surfaces

- `make remote-validate` replays the new bundle-aware repo automation on the build-server path
- `make pre-push-gate` replays the same generated-catalog contract through the heavy validation path
- `python3 config/windmill/scripts/post-merge-gate.py --repo-path /srv/proxmox_florin_server` validates the bundle-aware generated-catalog flow from the mirrored worker checkout after the live sync

## Branch-Local Progress

- the initial implementation seeds `catalog/services/_metadata.yaml` plus one `service.yaml` bundle per governed service from the current aggregates
- `scripts/service_definition_catalog.py --check` now proves the generated aggregates match the bundle source tree, and `make scaffold-service` switches to writing a service bundle when the metadata exists
- focused validation is currently green for the new assembler, the scaffold bundle mode, the existing `service_catalog.py` query path, and the downstream SLO generator surfaces assembled from `config/slo-catalog.json`

## Pending Mainline Follow-Through

- finish the wider validation replay and preserve the evidence in `receipts/live-applies/evidence/`
- update ADR 0324 implementation metadata and record the canonical live-apply receipt once the exact-main replay is verified
- refresh the protected release surfaces only during the final mainline integration step
