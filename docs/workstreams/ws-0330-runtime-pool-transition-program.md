# Workstream ws-0330-runtime-pool-transition-program: Complete The Runtime Pool Transition Program

- ADR: [ADR 0319](../adr/0319-runtime-pools-as-the-service-partition-boundary.md), [ADR 0320](../adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md), [ADR 0321](../adr/0321-runtime-pool-memory-envelopes-and-reserved-host-headroom.md), [ADR 0322](../adr/0322-memory-pressure-autoscaling-for-elastic-runtime-pools.md), [ADR 0323](../adr/0323-service-mobility-tiers-and-migration-waves-for-runtime-pools.md)
- Title: Finish the phased runtime-pool transition after the first `runtime-ai` live apply
- Status: in_progress
- Branch: `codex/ws-0330-runtime-pools-transition`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0324-runtime-pools-transition`
- Owner: codex
- Depends On: `adr-0319-runtime-pools-as-the-service-partition-boundary`, `adr-0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes`, `adr-0321-runtime-pool-memory-envelopes-and-reserved-host-headroom`, `adr-0322-memory-pressure-autoscaling-for-elastic-runtime-pools`, `adr-0323-service-mobility-tiers-and-migration-waves-for-runtime-pools`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0330-runtime-pool-transition-program.md`, `config/service-capability-catalog.json`, `config/contracts/service-partitions/`, `docs/schema/service-capability-catalog.schema.json`, `docs/schema/service-partition-catalog.schema.json`, `scripts/generate_platform_vars.py`, `scripts/validate_repository_data_models.py`, `inventory/group_vars/platform.yml`, `tests/test_generate_platform_vars.py`, `tests/test_runtime_pool_service_classification.py`

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

This branch starts with **Phase 1**. Later phases remain in the same program,
but should only land when the classification metadata and generated platform
truth are stable enough to support them.

## Verification Plan

- validate the service catalog and generated platform vars after the metadata
  backfill
- add regression tests that assert the catalog and generated topology expose
  the new classification fields for representative services
- run the relevant repository data-model and generated-doc checks before
  merging
