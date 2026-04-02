# Workstream ws-0330-runtime-pool-transition-program: Complete The Runtime Pool Transition Program

- ADR: [ADR 0319](../adr/0319-runtime-pools-as-the-service-partition-boundary.md), [ADR 0320](../adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md), [ADR 0321](../adr/0321-runtime-pool-memory-envelopes-and-reserved-host-headroom.md), [ADR 0322](../adr/0322-memory-pressure-autoscaling-for-elastic-runtime-pools.md), [ADR 0323](../adr/0323-service-mobility-tiers-and-migration-waves-for-runtime-pools.md)
- Title: Finish the phased runtime-pool transition after the first `runtime-ai` live apply
- Status: in_progress
- Branch: `codex/ws-0330-runtime-pools-transition`
- Worktree: `.worktrees/ws-0324-runtime-pools-transition`
- Owner: codex
- Depends On: `adr-0319-runtime-pools-as-the-service-partition-boundary`, `adr-0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes`, `adr-0321-runtime-pool-memory-envelopes-and-reserved-host-headroom`, `adr-0322-memory-pressure-autoscaling-for-elastic-runtime-pools`, `adr-0323-service-mobility-tiers-and-migration-waves-for-runtime-pools`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0330-runtime-pool-transition-program.md`, `config/service-capability-catalog.json`, `config/contracts/service-partitions/`, `docs/schema/service-capability-catalog.schema.json`, `docs/schema/service-partition-catalog.schema.json`, `scripts/generate_platform_vars.py`, `scripts/validate_repository_data_models.py`, `inventory/hosts.yml`, `inventory/group_vars/all.yml`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `config/execution-lanes.yaml`, `config/ansible-execution-scopes.yaml`, `config/health-probe-catalog.json`, `config/service-redundancy-catalog.json`, `config/slo-catalog.json`, `config/prometheus/file_sd/slo_targets.yml`, `config/subdomain-exposure-registry.json`, `config/workflow-catalog.json`, `config/capacity-model.json`, `docs/schema/capacity-model.schema.json`, `scripts/capacity_report.py`, `config/runtime-pool-autoscaling.json`, `docs/schema/runtime-pool-autoscaling.schema.json`, `scripts/runtime_pool_autoscaling.py`, `playbooks/runtime-general-pool.yml`, `playbooks/services/runtime-general-pool.yml`, `playbooks/homepage.yml`, `playbooks/uptime-kuma.yml`, `playbooks/nomad.yml`, `collections/ansible_collections/lv3/platform/playbooks/mailpit.yml`, `collections/ansible_collections/lv3/platform/roles/runtime_pool_substrate/`, `docs/runbooks/configure-runtime-general-pool.md`, `docs/runbooks/configure-mailpit.md`, `docs/runbooks/deploy-uptime-kuma.md`, `docs/runbooks/configure-homepage.md`, `docs/runbooks/configure-nomad.md`, `docs/runbooks/runtime-pool-memory-governance.md`, `docs/runbooks/configure-runtime-pool-autoscaling.md`, `tests/test_generate_platform_vars.py`, `tests/test_runtime_pool_service_classification.py`, `tests/test_runtime_pool_substrate_role.py`, `tests/test_mailpit_playbook.py`, `tests/test_nomad_playbook.py`, `tests/test_homepage_runtime_role.py`, `tests/test_runtime_general_pool_playbook.py`, `tests/test_runtime_general_service_playbooks.py`, `tests/test_capacity_report.py`, `tests/test_runtime_pool_autoscaling.py`, `receipts/runtime-pool-scaling/.gitkeep`

## Purpose

Complete the practical follow-on work after ADR 0319 and ADR 0320 by first
classifying every repo-managed service into an explicit partition boundary,
mobility tier, and deployment surface, then using that metadata to drive the
next runtime-general, memory-envelope, autoscaling, and runtime-control waves.

## Phases

1. **Phase 1: Service classification metadata everywhere**
   - declare `runtime_pool`, `deployment_surface`, `restart_domain`,
     `api_contract_ref`, and `mobility_tier` for every service
   - make the service capability catalog the canonical classification source
   - project that metadata into generated platform vars so later pool work can
     use one shared classification model

2. **Phase 2: `runtime-general` pool implementation**
   - stand up a second pool-scoped deploy surface and execution lane
   - move lightweight operator and support surfaces out of `docker-runtime-lv3`

3. **Phase 3: ADR 0321 memory envelopes**
   - encode pool baselines, maxima, and the host free-memory floor in repo
     automation and validation

4. **Phase 4: ADR 0322 autoscaling**
   - add bounded memory-pressure autoscaling for eligible pools using the
     declared envelopes and eligibility metadata

5. **Phase 5: `runtime-control` migration**
   - move high-consequence anchors last, after the general and AI pools are
     stable and the control-plane migration runbooks are complete

## Current Scope

This branch started with **Phase 1**, moved into **Phase 2** by standing up
`runtime-general-lv3`, moving `uptime_kuma`, `status_page`, `homepage`, and
`mailpit`, and generalising the shared runtime-pool substrate, and now carries
the first repo-managed **Phase 3** and **Phase 4** contracts:

- `config/capacity-model.json.runtime_pool_memory` now governs the
  `runtime-control`, `runtime-general`, and `runtime-ai` envelopes plus the
  host free-memory floor from ADR 0321.
- `config/runtime-pool-autoscaling.json` now records the bounded first-phase
  Nomad Autoscaler policy for `runtime-general` and `runtime-ai` using
  Prometheus, Traefik, and Dapr as the preferred control surfaces from ADR
  0322.
- `homepage`, `status_page`, and `dozzle` are now explicitly classified as
  `elastic_stateless`, making the autoscaling gate reviewable instead of
  implicit.

## Verification Plan

- validate the service catalog and generated platform vars after the metadata
  backfill
- add regression tests that assert the catalog and generated topology expose
  the new classification fields for representative services
- syntax-check and test the new runtime-general pool deploy surface, service
  wrappers, and shared substrate role before attempting later live apply work
- validate the runtime-pool memory governance and autoscaling catalogs directly
  through `scripts/capacity_report.py` and `scripts/runtime_pool_autoscaling.py`
- run the relevant repository data-model and generated-doc checks before
  merging
