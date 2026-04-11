# Workstream ws-0330-runtime-pool-transition-program: Complete The Runtime Pool Transition Program

- ADR: [ADR 0319](../adr/0319-runtime-pools-as-the-service-partition-boundary.md), [ADR 0320](../adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md), [ADR 0321](../adr/0321-runtime-pool-memory-envelopes-and-reserved-host-headroom.md), [ADR 0322](../adr/0322-memory-pressure-autoscaling-for-elastic-runtime-pools.md), [ADR 0323](../adr/0323-service-mobility-tiers-and-migration-waves-for-runtime-pools.md)
- Title: Finish the phased runtime-pool transition after the first `runtime-ai` live apply
- Status: merged
- Branch: `codex/ws-0330-runtime-pools-transition`
- Worktree: `.worktrees/ws-0324-runtime-pools-transition`
- Owner: codex
- Depends On: `adr-0319-runtime-pools-as-the-service-partition-boundary`, `adr-0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes`, `adr-0321-runtime-pool-memory-envelopes-and-reserved-host-headroom`, `adr-0322-memory-pressure-autoscaling-for-elastic-runtime-pools`, `adr-0323-service-mobility-tiers-and-migration-waves-for-runtime-pools`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0330-runtime-pool-transition-program.md`, `config/service-capability-catalog.json`, `config/contracts/service-partitions/`, `docs/schema/service-capability-catalog.schema.json`, `docs/schema/service-partition-catalog.schema.json`, `scripts/generate_platform_vars.py`, `scripts/validate_repository_data_models.py`, `inventory/hosts.yml`, `inventory/group_vars/all.yml`, `inventory/host_vars/proxmox-host.yml`, `inventory/group_vars/platform.yml`, `config/execution-lanes.yaml`, `config/ansible-execution-scopes.yaml`, `config/api-gateway-catalog.json`, `config/control-plane-lanes.json`, `config/health-probe-catalog.json`, `config/service-redundancy-catalog.json`, `config/slo-catalog.json`, `config/prometheus/file_sd/slo_targets.yml`, `config/prometheus/rules/slo_alerts.yml`, `config/subdomain-exposure-registry.json`, `config/uptime-kuma/monitors.json`, `config/workflow-catalog.json`, `config/capacity-model.json`, `config/grafana/dashboards/slo-overview.json`, `docs/schema/capacity-model.schema.json`, `scripts/capacity_report.py`, `config/runtime-pool-autoscaling.json`, `docs/schema/runtime-pool-autoscaling.schema.json`, `scripts/runtime_pool_autoscaling.py`, `playbooks/runtime-general-pool.yml`, `playbooks/services/runtime-general-pool.yml`, `playbooks/runtime-control-pool.yml`, `playbooks/services/runtime-control-pool.yml`, `playbooks/api-gateway.yml`, `playbooks/gitea.yml`, `playbooks/harbor.yml`, `playbooks/homepage.yml`, `playbooks/keycloak.yml`, `playbooks/mail-platform-diagnostics.yml`, `playbooks/mail-platform-notification-profiles-verify.yml`, `playbooks/mail-platform-send-gmail.yml`, `playbooks/mail-platform.yml`, `playbooks/nats-jetstream.yml`, `playbooks/nomad.yml`, `playbooks/openbao.yml`, `playbooks/openfga.yml`, `playbooks/semaphore.yml`, `playbooks/step-ca.yml`, `playbooks/temporal.yml`, `playbooks/uptime-kuma.yml`, `playbooks/vaultwarden.yml`, `playbooks/windmill.yml`, `collections/ansible_collections/lv3/platform/playbooks/mail-platform-verify.yml`, `collections/ansible_collections/lv3/platform/playbooks/mailpit.yml`, `collections/ansible_collections/lv3/platform/roles/runtime_pool_substrate/`, `docs/runbooks/configure-runtime-general-pool.md`, `docs/runbooks/configure-runtime-control-pool.md`, `docs/runbooks/configure-gitea.md`, `docs/runbooks/configure-harbor.md`, `docs/runbooks/configure-keycloak.md`, `docs/runbooks/configure-mail-platform.md`, `docs/runbooks/configure-mailpit.md`, `docs/runbooks/configure-homepage.md`, `docs/runbooks/configure-nomad.md`, `docs/runbooks/configure-openbao.md`, `docs/runbooks/configure-openfga.md`, `docs/runbooks/configure-runtime-pool-autoscaling.md`, `docs/runbooks/configure-semaphore.md`, `docs/runbooks/configure-step-ca.md`, `docs/runbooks/configure-temporal.md`, `docs/runbooks/configure-vaultwarden.md`, `docs/runbooks/configure-windmill.md`, `docs/runbooks/deploy-uptime-kuma.md`, `docs/runbooks/runtime-pool-memory-governance.md`, `tests/test_generate_platform_vars.py`, `tests/test_runtime_pool_service_classification.py`, `tests/test_runtime_pool_substrate_role.py`, `tests/test_mailpit_playbook.py`, `tests/test_mail_platform_runtime_role.py`, `tests/test_mail_platform_verify_playbook.py`, `tests/test_nomad_playbook.py`, `tests/test_homepage_runtime_role.py`, `tests/test_openbao_playbook.py`, `tests/test_openfga_metadata.py`, `tests/test_openfga_runtime_role.py`, `tests/test_harbor_runtime_role.py`, `tests/test_nats_jetstream_runtime_role.py`, `tests/test_runtime_control_pool_playbook.py`, `tests/test_runtime_general_pool_playbook.py`, `tests/test_runtime_general_service_playbooks.py`, `tests/test_temporal_playbook.py`, `tests/test_capacity_report.py`, `tests/test_runtime_pool_autoscaling.py`, `receipts/runtime-pool-scaling/.gitkeep`

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
   - move lightweight operator and support surfaces out of `docker-runtime`

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

This workstream started with **Phase 1**, moved into **Phase 2** by standing up
`runtime-general`, moving `uptime_kuma`, `status_page`, `homepage`, and
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

The branch now also carries the repo-managed **Phase 5** runtime-control wave:

- `runtime-control` is declared as the fixed-capacity control-plane guest
  with its own execution lane, capacity envelope, and Proxmox inventory
  contract.
- `playbooks/runtime-control-pool.yml` and
  `playbooks/services/runtime-control-pool.yml` now define the end-to-end
  runtime-control migration surface, including Traefik plus Dapr substrate
  verification, Nomad namespace bootstrap, service imports, and retirement of
  the legacy control-plane copies on `docker-runtime`.
- the control-plane service metadata, health probes, proxy contracts, and
  runbooks now point at `runtime-control` for the moved `api_gateway`,
  `gitea`, `harbor`, `keycloak`, `mail_platform`, `nats_jetstream`,
  `openbao`, `openfga`, `semaphore`, `step_ca`, `temporal`, `vaultwarden`,
  and `windmill` slice.
- this phase is now merged as a repo-only change and still awaits a guarded
  live apply from integrated `main`.

## Verification Plan

- validate the service catalog and generated platform vars after the metadata
  backfill
- add regression tests that assert the catalog and generated topology expose
  the new classification fields for representative services
- syntax-check and test the new runtime-general pool deploy surface, service
  wrappers, and shared substrate role before attempting later live apply work
- syntax-check and test the runtime-control pool playbook, representative
  control-service playbooks, and the control-plane mail verification flow
- validate the runtime-pool memory governance and autoscaling catalogs directly
  through `scripts/capacity_report.py` and `scripts/runtime_pool_autoscaling.py`
- regenerate the platform vars, SLO targets, uptime monitor catalog, and
  subdomain exposure registry after control-plane metadata changes
- run the relevant repository data-model and generated-doc checks before
  merging

## Completed Verification

- `uv run --with pytest --with pyyaml pytest -q tests/test_nomad_playbook.py tests/test_openbao_playbook.py tests/test_openfga_metadata.py tests/test_openfga_runtime_role.py tests/test_mail_platform_verify_playbook.py tests/test_mail_platform_runtime_role.py tests/test_harbor_runtime_role.py tests/test_nats_jetstream_runtime_role.py tests/test_temporal_playbook.py tests/test_runtime_control_pool_playbook.py tests/test_generate_platform_vars.py tests/test_runtime_general_pool_playbook.py tests/test_runtime_general_service_playbooks.py tests/test_runtime_pool_substrate_role.py tests/test_capacity_report.py tests/test_runtime_pool_autoscaling.py`
  passed with `121` tests green.
- `scripts/validate_repo.sh agent-standards data-models workstream-surfaces`
  passed.
- `uv run --with pyyaml python scripts/runtime_pool_autoscaling.py --check`
  passed and confirmed the bounded autoscaling catalog for `runtime-general`
  and `runtime-ai`.
- `uv run --with pyyaml python scripts/capacity_report.py --format json
  --no-live-metrics` confirmed the ADR 0321 pool baselines, maxima, and
  20 GiB host free-memory floor contract.
- `uv run --with pyyaml python scripts/capacity_report.py --check-gate
  --no-live-metrics` still reports the broader host-wide estate is over the
  global target commitment; that pre-existing capacity issue remains separate
  from this repo-managed runtime-pool transition.

## Remaining Live Apply Work

- run the guarded mainline live apply for `playbooks/runtime-control-pool.yml`
  and the moved control-plane service playbooks
- verify the actual `runtime-control` guest exists live before retiring the
  legacy control-plane copies on `docker-runtime`
- reconcile the wider host commitment model before treating ADR 0321 gate
  failures as a pool-specific regression
