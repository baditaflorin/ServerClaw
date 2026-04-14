# Workstream ws-0324-live-apply: Live Apply ADR 0324 From Latest `origin/main`

- ADR: [ADR 0324](../adr/0324-service-definition-shards-and-generated-service-catalog-assembly.md)
- Title: Implement ADR 0324 by moving service metadata into per-service bundles and verifying the generated-catalog automation end to end
- Status: live_applied
- Included In Repo Version: `0.178.140`
- Branch-Local Receipt: `receipts/live-applies/2026-04-04-adr-0324-service-definition-catalog-assembly-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-14-adr-0324-service-definition-catalog-assembly-mainline-live-apply.json`
- Implemented On: 2026-04-04
- Live Applied On: 2026-04-04
- Live Applied In Platform Version: 0.130.98
- Latest Verified Base: `origin/main@4bb9c2fd7c8a3296e33a8dc7e77ee06bd5adf0a4` (`VERSION 0.178.140`, `stack repo 0.178.139`, `platform 0.178.138`)
- Branch: `codex/ws-0324-main-integration-r5`
- Worktree: `.worktrees/ws-0324-main-integration-r5`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0107-platform-extension-model`, `adr-0174-integration-only-canonical-truth-assembly`, `adr-0179-service-redundancy-tier-matrix`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0324-live-apply.md`, `docs/adr/0324-service-definition-shards-and-generated-service-catalog-assembly.md`, `docs/adr/.index.yaml`, `docs/adr/index/by-range/*.yaml`, `docs/adr/index/by-concern/*.yaml`, `docs/adr/index/by-status/*.yaml`, `.repo-structure.yaml`, `.config-locations.yaml`, `build/onboarding/agent-core.yaml`, `build/onboarding/automation.yaml`, `build/onboarding/service-catalog.yaml`, `catalog/services/`, `docs/discovery/config-locations/service-configuration.yaml`, `docs/discovery/repo-structure/automation-and-infrastructure.yaml`, `docs/discovery/repo-structure/cross-cutting-concerns.yaml`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/service-completeness.json`, `config/service-redundancy-catalog.json`, `config/dependency-graph.json`, `config/data-catalog.json`, `config/slo-catalog.json`, `config/prometheus/rules/slo_rules.yml`, `config/prometheus/rules/slo_alerts.yml`, `config/prometheus/file_sd/slo_targets.yml`, `config/grafana/dashboards/slo-overview.json`, `docs/schema/service-definition-*.json`, `docs/schema/health-probe-catalog.schema.json`, `docs/runbooks/service-capability-catalog.md`, `docs/runbooks/add-a-new-service.md`, `docs/runbooks/scaffold-new-service.md`, `.yamllint`, `Makefile`, `scripts/service_definition_catalog.py`, `scripts/service_catalog.py`, `scripts/scaffold_service.py`, `scripts/validate_repo.sh`, `tests/test_service_definition_catalog.py`, `tests/test_scaffold_service.py`, `tests/test_validate_service_catalog.py`, `docs/diagrams/agent-coordination-map.excalidraw`, `receipts/live-applies/*0324*`, `receipts/live-applies/evidence/2026-04-03-ws-0324-*`, `receipts/live-applies/evidence/2026-04-04-ws-0324-*`, `receipts/live-applies/evidence/2026-04-14-ws-0324-*`, `README.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`

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
- `docs/discovery/config-locations/service-configuration.yaml`
- `docs/discovery/repo-structure/automation-and-infrastructure.yaml`
- `docs/discovery/repo-structure/cross-cutting-concerns.yaml`
- `build/onboarding/agent-core.yaml`
- `build/onboarding/automation.yaml`
- `build/onboarding/service-catalog.yaml`
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

## Outcome

- `catalog/services/_metadata.yaml` plus one `service.yaml` bundle per governed service now act as the ADR 0324 source tree for service-local metadata, and the aggregate service catalogs are assembled from those bundles instead of being hand-edited monoliths.
- `scripts/service_definition_catalog.py --check` proves the generated aggregate surfaces match the bundle source tree, while `scripts/scaffold_service.py` now scaffolds service bundles when the catalog metadata exists.
- The live-apply follow-through on the latest `origin/main` also hardened the runtime validation path that consumes the generated service metadata from the Windmill worker mirror: the worker checkout now preserves its mutable `.local/validation-gate` paths, includes generated discovery entrypoints needed by the post-merge gate, and uses the externally reachable Windmill base URL for controller-side verification calls.

## Verification

- Focused branch-local regression coverage passed on the rebased exact-main tree: `uv run --with pytest --with pyyaml --with jsonschema python3 -m pytest -q tests/test_service_definition_catalog.py tests/test_scaffold_service.py tests/test_validate_service_catalog.py tests/test_sync_windmill_resources.py tests/test_windmill_operator_admin_app.py tests/test_common_docker_bridge_chains_helper.py tests/test_docker_runtime_role.py tests/test_linux_guest_firewall_role.py tests/test_postgres_vm_access_policy.py tests/test_windmill_default_operations_surface.py`, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0324-rebased-pytest-r3-0.178.3.txt`, with `61 passed in 29.55s`.
- Windmill-focused follow-up regression slices then passed after the worker-checkout and controller-verification fixes: `25 passed in 1.24s` and `18 passed in 0.68s`, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0324-windmill-verification-tests-r1-0.178.3.txt` and `receipts/live-applies/evidence/2026-04-04-ws-0324-windmill-verification-tests-r2-0.178.3.txt`.
- `uv run --with pyyaml --with jsonschema python3 scripts/service_definition_catalog.py --check`, `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate`, `./scripts/validate_repo.sh agent-standards workstream-surfaces`, and `git diff --check` all passed on the receipt-bearing branch state, preserved in the matching `2026-04-04-ws-0324-rebased-*.txt` evidence files.
- The initial exact-main `make converge-windmill` replay succeeded and is preserved in `receipts/live-applies/evidence/2026-04-04-ws-0324-mainline-converge-windmill-r8-0.178.3.txt`. A later replay exposed two real live issues that this workstream fixed: the worker mirror was missing writable `.local/validation-gate` paths and generated discovery files, and the controller-side verify tasks were trying to reach the private Windmill address instead of the routable base URL.
- A bounded manual live sync copied `.repo-structure.yaml`, `.config-locations.yaml`, and `build/onboarding/*.yaml` into `/srv/proxmox_florin_server` after the worker fallback exposed that mirror gap, and the repo automation now includes the permanent sync-path fix so later replays do not need that manual copy.
- The latest worker `post-merge-gate` replay now reaches a healthy Docker attestation and falls back locally for the expected registry-runner outage, but the remaining failure is only stale canonical-truth on `/srv/proxmox_florin_server/changelog.md` and `/srv/proxmox_florin_server/versions/stack.yaml`, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0324-worker-post-merge-gate-r3-0.178.3.txt`. Those protected surfaces are intentionally deferred to the final exact-main integration step.
- The follow-up exact-main `make converge-windmill` replay no longer hangs in the controller verification block after switching to `windmill_base_url`; the remaining `sudo` timeout at `Create a remote manifest path for repo-managed Windmill scripts` is a later privilege-escalation flake rather than a regression in the ADR 0324 service-catalog path, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0324-mainline-converge-windmill-r10-0.178.3.txt`.
- On the latest realistic `origin/main@4bb9c2fd7c8a3296e33a8dc7e77ee06bd5adf0a4`, `uv run --with pyyaml --with jsonschema python3 scripts/service_definition_catalog.py --check` passed from the fresh exact-main integration worktree before the final release cut; the 2026-04-14 evidence file is recorded alongside the final mainline receipt.
- The fresh exact-main validation replay also reproduced one current-main generated-artifact gap rather than an ADR 0324 regression: `config/prometheus/file_sd/slo_targets.yml` was missing from `origin/main` and had to be regenerated before the repository data-model gate could pass again. That repair is recorded in the 2026-04-14 exact-main evidence set and is now part of the integrated mainline closeout.

## Exact-Main Integration Status

- ADR 0324 remains first-live-proven on platform version `0.130.98`, and this exact-main closeout carries that already-verified implementation into the current mainline repo version `0.178.140` from the latest realistic `origin/main` base.
- The final integration step updates the protected main-only surfaces from source, records the mainline receipt, and reruns the promotion-facing validation and worker post-merge verification from `main`. A fresh numbered release cut remains intentionally deferred because unrelated active workstreams still trip the repository's `release_manager.py` blocker policy.
- The clean latest-main verification workspace at `origin/main@4bb9c2fd7c8a3296e33a8dc7e77ee06bd5adf0a4` is already red in the broader promotion gate on `generated-docs`, `ansible-lint`, and `integration-tests`, so those failures remain inherited mainline debt rather than new ADR 0324 regressions. The ws-0324 exact-main replay repaired its own ADR index drift and image-scan receipt materialization gap, while the focused catalog, receipt, and remote-validate paths stayed green on the rebased tree.
