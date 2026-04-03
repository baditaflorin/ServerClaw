# Proxmox Reference Platform

Forkable infrastructure-as-code reference for taking a Debian 13 host to a
repo-managed Proxmox VE platform.

This repository is being prepared for public GitHub publication. The committed
root surfaces now prefer generic language, repo-relative links, and portable
metadata so another team can clone, fork, and adapt the platform without first
rewriting one operator's workstation paths.

## What This Repo Includes

- architecture decisions in `docs/adr/`
- operational runbooks in `docs/runbooks/`
- parallel-workstream tracking in `workstreams.yaml`
- automation and validation under `collections/`, `playbooks/`, `scripts/`,
  and `tests/`
- generated status and release surfaces that summarize current integrated
  repository truth

## Forking Guidance

1. Read `README.md`, `AGENTS.md`, `.repo-structure.yaml`,
   `.config-locations.yaml`, `docs/adr/.index.yaml`, and `workstreams.yaml`.
2. Replace deployment-specific inventory, hostnames, provider choices, and
   secrets with your own values before any live apply.
3. Keep personal machine paths, operator-specific credentials, and local
   bootstrap artefacts in ignored `.local/` state or environment variables.
4. Prefer repo-relative paths in committed metadata so worktrees, CI runners,
   and new forks all resolve the same contracts.

## Public Readiness

- public entrypoints are validated to reject committed workstation home paths
- workstream metadata now uses repository-relative docs and worktree paths
- release-note and status generators now emit repo-relative links
- the new ADR 0330-0339 bundle defines the remaining public-template and
  private-overlay work needed to keep the repo reproducible for forks

<!-- BEGIN GENERATED: platform-status -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

### Current Values
| Field | Value |
| --- | --- |
| Repository version | `0.178.2` |
| Platform version | `0.130.98` |
| Observed check date | `2026-04-03` |
| Observed OS | `Debian 13` |
| Observed Proxmox version | `9.1.6` |
| Observed kernel | `6.17.13-2-pve` |

### Topology Summary
| Field | Value |
| --- | --- |
| Managed guest count | 13 |
| Running guest count | 10 |
| Template VM present | `true` |
| Declared services | 72 |
| Publicly published services | 45 |

### Service Exposure Summary
| Exposure Model | Services |
| --- | --- |
| `edge-published` | 36 |
| `edge-static` | 1 |
| `informational-only` | 4 |
| `private-only` | 31 |

### Latest Live-Apply Evidence
| Capability | Receipt |
| --- | --- |
| `agent_coordination` | `2026-03-26-adr-0161-real-time-agent-coordination-map-live-apply` |
| `api_gateway` | `2026-03-29-adr-0245-declared-to-live-service-attestation-live-apply` |
| `artifact_cache_plane` | `2026-03-29-adr-0295-shared-artifact-cache-plane-mainline-live-apply` |
| `artifact_cache_vm` | `2026-03-30-adr-0296-dedicated-artifact-cache-vm-mainline-live-apply` |
| `backup_coverage` | `2026-03-29-adr-0271-backup-coverage-ledger-mainline-live-apply` |
| `backup_vm` | `2026-03-22-adr-0029-backup-vm-live-apply` |
| `bounded_command_execution` | `2026-03-28-adr-0227-bounded-command-execution-mainline-live-apply` |
| `browser_runner` | `2026-03-30-adr-0261-playwright-browser-runners-live-apply` |
| `budgeted_workflow_scheduler` | `2026-03-27-adr-0119-budgeted-workflow-scheduler-mainline-live-apply` |
| `build_telemetry` | `2026-03-22-adr-0028-build-telemetry-live-apply` |
| `canonical_publication_models` | `2026-03-28-adr-0210-canonical-domain-models-live-apply` |
| `capability_contracts` | `2026-03-28-adr-0205-capability-contracts-before-product-selection-mainline-live-apply` |
| `capacity_classes` | `2026-03-27-adr-0192-capacity-classes-live-apply` |
| `capacity_model` | `2026-03-27-adr-0105-capacity-model-mainline-live-apply` |
| `certificate_lifecycle` | `2026-03-27-adr-0101-certificate-lifecycle-main-live-apply` |
| `changedetection` | `2026-03-30-adr-0280-changedetection-mainline-live-apply` |
| `command_catalog` | `2026-03-28-adr-0230-policy-decisions-live-apply` |
| `command_palette` | `2026-04-02-adr-0311-global-command-palette-mainline-live-apply` |
| `config_merge` | `2026-03-26-adr-0158-config-merge-live-apply` |
| `control_metadata_witness` | `2026-03-27-adr-0181-control-metadata-witness-live-apply` |
| `control_plane_lanes` | `2026-03-22-adr-0045-control-plane-communication-lanes-live-apply` |
| `control_plane_recovery` | `2026-03-28-adr-0231-local-secret-delivery-live-apply` |
| `coolify` | `2026-03-30-adr-0274-governed-base-image-mirrors-and-warm-caches-mainline-live-apply` |
| `coolify_apps` | `2026-04-03-adr-0340-coolify-apps-vm-separation-live-apply` |
| `crawl4ai` | `2026-03-31-adr-0288-crawl4ai-mainline-live-apply` |
| `database_schema` | `2026-04-02-adr-0304-atlas-mainline-live-apply` |
| `deadlock_detector` | `2026-03-26-adr-0162-deadlock-detector-live-apply` |
| `dependency_graph_runtime` | `2026-03-26-adr-0117-dependency-graph-live-apply` |
| `dify` | `2026-03-28-adr-0197-dify-mainline-live-apply` |
| `directus` | `2026-03-30-adr-0289-directus-mainline-live-apply` |
| `docker_publication` | `2026-03-30-adr-0270-docker-publication-self-healing-and-port-programming-assertions-mainline-live-apply` |
| `docker_runtime` | `2026-03-22-adr-0023-docker-runtime-live-apply` |
| `docs_portal` | `2026-04-02-adr-0313-contextual-help-mainline-live-apply` |
| `dozzle` | `2026-03-26-adr-0150-dozzle-live-apply` |
| `excalidraw` | `2026-03-27-adr-0202-excalidraw-auto-generated-architecture-diagrams-live-apply` |
| `failure_domain_policy` | `2026-03-27-adr-0184-failure-domain-labels-live-apply` |
| `falco` | `2026-04-03-adr-0300-falco-mainline-live-apply` |
| `fixture_pools` | `2026-03-28-adr-0186-prewarmed-fixture-pools-live-apply` |
| `flagsmith` | `2026-03-30-adr-0288-flagsmith-mainline-live-apply` |
| `gitea` | `2026-03-26-adr-0143-gitea-live-apply` |
| `gitea_actions_runners` | `2026-03-28-adr-0229-gitea-actions-runners-live-apply` |
| `glitchtip` | `2026-04-03-adr-0281-glitchtip-mainline-live-apply` |
| `gotenberg` | `2026-04-02-adr-0319-runtime-ai-pool-mainline-live-apply` |
| `grist` | `2026-04-01-adr-0279-grist-mainline-live-apply` |
| `guest_network_policy` | `2026-03-22-adr-0067-guest-network-policy-live-apply` |
| `harbor` | `2026-03-29-adr-0201-harbor-mainline-live-apply` |
| `homepage` | `2026-04-03-ws-0332-homepage-triage-mainline-live-apply` |
| `host_control_loops` | `2026-03-28-adr-0226-host-control-loops-mainline-live-apply` |
| `https_tls_assurance` | `2026-03-29-adr-0255-matrix-synapse-mainline-live-apply` |
| `iac_policy_scanning` | `2026-03-31-adr-0306-checkov-iac-policy-scan-mainline-live-apply` |
| `identity_taxonomy` | `2026-03-22-adr-0046-identity-classes-live-apply` |
| `immutable_guest_replacement` | `2026-03-27-adr-0191-immutable-guest-replacement-live-apply` |
| `journey_analytics` | `2026-04-02-adr-0316-journey-analytics-mainline-live-apply` |
| `jupyterhub` | `2026-03-30-adr-0291-jupyterhub-mainline-live-apply` |
| `k6_load_testing` | `2026-03-31-adr-0305-k6-mainline-live-apply` |
| `keycloak` | `2026-03-30-adr-0262-openfga-keycloak-mainline-live-apply` |
| `keycloak_direct_api` | `2026-04-02-adr-0317-keycloak-direct-api-mainline-live-apply` |
| `keycloak_operator_access` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `label_studio` | `2026-04-03-adr-0289-label-studio-mainline-live-apply` |
| `lago` | `2026-04-01-adr-0292-lago-mainline-live-apply` |
| `langfuse` | `2026-03-26-adr-0146-langfuse-live-apply` |
| `livekit` | `2026-04-01-adr-0293-livekit-mainline-live-apply` |
| `local_search_and_indexing_fabric` | `2026-03-29-adr-0239-browser-local-search-post-merge-replay` |
| `log_queryability_canary` | `2026-03-28-adr-0250-log-queryability-canary-live-apply` |
| `mail_platform` | `2026-03-24-keycloak-password-reset-mail-live-apply` |
| `mailpit` | `2026-03-30-adr-0282-mailpit-mainline-live-apply` |
| `matrix_synapse` | `2026-03-29-adr-0255-matrix-synapse-mainline-live-apply` |
| `mattermost` | `2026-03-23-adr-0077-compose-runtime-secrets-live-apply` |
| `minio` | `2026-03-31-adr-0274-minio-object-storage-mainline-live-apply` |
| `monitoring` | `2026-03-28-adr-0250-log-queryability-canary-live-apply` |
| `mutation_audit` | `2026-03-23-adr-0066-mutation-audit-live-apply` |
| `mutation_ledger` | `2026-03-27-adr-0115-mutation-ledger-mainline-live-apply` |
| `n8n` | `2026-03-29-adr-0259-n8n-serverclaw-connector-fabric-mainline-live-apply` |
| `nats_jetstream` | `2026-03-30-adr-0276-nats-jetstream-event-bus-mainline-live-apply` |
| `netbox` | `2026-03-23-adr-0077-compose-runtime-secrets-live-apply` |
| `network_impairment_matrix` | `2026-03-27-adr-0189-network-impairment-matrix-live-apply` |
| `nextcloud` | `2026-03-30-adr-0260-nextcloud-personal-data-plane-mainline-live-apply` |
| `nomad_scheduler` | `2026-04-02-adr-0319-runtime-ai-pool-mainline-live-apply` |
| `notification_profiles` | `2026-03-22-adr-0050-notification-profiles-live-apply` |
| `ntfy` | `2026-04-03-adr-0299-ntfy-mainline-live-apply` |
| `ntopng` | `2026-03-22-adr-0059-ntopng-live-apply` |
| `observation_to_action_closure_loop` | `2026-03-26-adr-0126-observation-to-action-closure-loop-live-apply` |
| `ollama` | `2026-03-27-adr-0176-inventory-sharding-mainline-live-apply` |
| `one_api` | `2026-04-01-adr-0294-one-api-mainline-live-apply` |
| `open_webui` | `2026-04-01-adr-0294-one-api-mainline-live-apply` |
| `openbao` | `2026-03-30-adr-0251-stage-smoke-promotion-gates-mainline-live-apply` |
| `openbao_operator_entity` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `openbao_operator_policy` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `openfga` | `2026-03-30-adr-0262-openfga-keycloak-mainline-live-apply` |
| `operator_access` | `2026-04-02-adr-0315-canonical-page-states-mainline-live-apply` |
| `operator_access_composition_root` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_guided_onboarding` | `2026-03-28-adr-0242-guided-human-onboarding-live-apply` |
| `operator_access_inventory` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_ports` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_quarterly_review` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_review` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_runbooks` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_validation` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_workflows` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `ops_portal` | `2026-04-03-adr-0309-task-oriented-information-architecture-mainline-live-apply` |
| `ops_portal_visualizations` | `2026-03-29-adr-0240-operator-visualization-panels-mainline-live-apply` |
| `outline` | `2026-03-28-adr-0199-outline-living-knowledge-wiki-mainline-live-apply` |
| `paperless` | `2026-03-31-adr-0285-paperless-live-apply` |
| `piper` | `2026-03-31-adr-0284-piper-mainline-live-apply` |
| `plane` | `2026-03-28-adr-0193-plane-mainline-live-apply` |
| `platform_context` | `2026-04-01-adr-0294-one-api-mainline-live-apply` |
| `platform_event_taxonomy` | `2026-03-26-adr-0124-platform-event-taxonomy-live-apply` |
| `plausible_analytics` | `2026-03-30-adr-0283-plausible-analytics-mainline-live-apply` |
| `policy_validation` | `2026-03-28-adr-0230-policy-decisions-live-apply` |
| `portainer` | `2026-03-22-adr-0055-portainer-live-apply` |
| `postgres_audit` | `2026-03-31-adr-0303-pgaudit-mainline-live-apply` |
| `postgres_vm` | `2026-03-22-adr-0026-postgres-vm-live-apply` |
| `preview_environment` | `2026-03-27-adr-0185-ws-0185-live-apply-20260327t191234z` |
| `promotion_pipeline` | `2026-03-29-adr-0251-stage-smoke-promotion-gates-mainline-live-apply` |
| `provider_boundaries` | `2026-03-28-adr-0207-anti-corruption-layers-at-provider-boundaries-live-apply` |
| `public_edge_publication` | `2026-03-29-adr-0255-matrix-synapse-mainline-live-apply` |
| `public_endpoint_admission_control` | `2026-03-29-adr-0273-public-endpoint-admission-control-mainline-live-apply` |
| `realtime` | `2026-03-27-adr-0196-netdata-realtime-streaming-metrics-live-apply` |
| `redpanda` | `2026-03-31-adr-0290-redpanda-mainline-live-apply` |
| `remote_build_gateway` | `2026-03-29-adr-0265-immutable-validation-snapshots-mainline-live-apply` |
| `renovate` | `2026-03-31-adr-0297-renovate-mainline-live-apply` |
| `repo_deploy_base_image_cache` | `2026-03-30-adr-0274-governed-base-image-mirrors-and-warm-caches-mainline-live-apply` |
| `restic_config_backup` | `2026-03-31-adr-0302-restic-config-backup-mainline-live-apply` |
| `restore_verification` | `2026-03-29-adr-0272-restore-readiness-mainline-live-apply` |
| `route_dns_assertion_ledger` | `2026-03-29-adr-0273-public-endpoint-admission-control-mainline-live-apply` |
| `runtime_container_telemetry` | `2026-03-22-adr-0040-runtime-container-telemetry-live-apply` |
| `runtime_state_semantics` | `2026-03-28-adr-0246-runtime-state-semantics-live-apply` |
| `sbom_cve_scanning` | `2026-03-31-adr-0298-sbom-cve-scanning-mainline-live-apply` |
| `searxng` | `2026-03-26-adr-0148-searxng-live-apply` |
| `secret_rotation` | `2026-03-23-adr-0065-secret-rotation-live-apply` |
| `security_posture_reporting` | `2026-03-26-adr-0102-security-posture-live-apply` |
| `seed_data_snapshots` | `2026-03-28-adr-0187-anonymized-seed-data-snapshots-mainline-live-apply` |
| `self_correcting_automation_loops` | `2026-03-28-adr-0204-self-correcting-automation-loops-live-apply` |
| `semaphore` | `2026-03-25-adr-0149-semaphore-live-apply` |
| `server_resident_operations` | `2026-03-28-adr-0224-server-resident-operations-default-control-live-apply` |
| `server_resident_reconciliation` | `2026-03-28-adr-0225-server-resident-reconciliation-via-ansible-pull-live-apply` |
| `serverclaw` | `2026-04-01-adr-0294-one-api-mainline-live-apply` |
| `serverclaw_memory` | `2026-03-29-adr-0263-serverclaw-memory-substrate-mainline-live-apply` |
| `serverclaw_skills` | `2026-03-31-adr-0257-serverclaw-skill-packs-mainline-live-apply` |
| `service_redundancy` | `2026-03-27-adr-0188-failover-rehearsal-gate-live-apply` |
| `session_logout_authority` | `2026-03-29-adr-0248-session-logout-authority-mainline-live-apply` |
| `shared_policy_packs` | `2026-03-28-adr-0211-shared-policy-packs-and-rule-registries-mainline-live-apply` |
| `short_lived_credentials_and_mtls` | `2026-03-22-adr-0047-short-lived-credentials-live-apply` |
| `signed_release_bundles` | `2026-03-28-adr-0233-signed-release-bundles-mainline-live-apply` |
| `stage_smoke_suites` | `2026-03-29-adr-0251-stage-smoke-promotion-gates-mainline-live-apply` |
| `staging_environment` | `2026-03-27-adr-0183-staging-live-apply` |
| `step_ca` | `2026-03-27-adr-0101-certificate-lifecycle-main-live-apply` |
| `superset` | `2026-04-01-adr-0292-superset-mainline-live-apply` |
| `tempo_tracing` | `2026-03-22-adr-0053-tempo-traces-live-apply` |
| `temporal` | `2026-03-30-adr-0293-temporal-mainline-live-apply` |
| `tesseract_ocr` | `2026-04-02-adr-0319-runtime-ai-pool-mainline-live-apply` |
| `tika` | `2026-04-02-adr-0319-runtime-ai-pool-mainline-live-apply` |
| `typesense` | `2026-03-31-adr-0277-typesense-mainline-live-apply` |
| `uptime_kuma` | `2026-04-03-ws-0332-homepage-triage-mainline-live-apply` |
| `validation_gate` | `2026-03-29-adr-0264-failure-domain-isolated-validation-lanes-mainline-live-apply` |
| `validation_runner_contracts` | `2026-03-29-adr-0266-validation-runner-capability-contracts-mainline-live-apply` |
| `vaultwarden` | `2026-03-29-adr-0252-route-and-dns-publication-assertion-ledger-mainline-live-apply` |
| `vulnerability_budget_gate` | `2026-03-30-adr-0269-vulnerability-budget-gates-mainline-live-apply` |
| `windmill` | `2026-03-29-adr-0228-windmill-default-operations-surface-mainline-live-apply` |
| `woodpecker` | `2026-03-30-adr-0287-woodpecker-mainline-live-apply` |
| `world_state_materializer` | `2026-03-27-adr-0113-world-state-materializer-mainline-live-apply` |
<!-- END GENERATED: platform-status -->

The current access posture is:

```text
ops SSH + sudo for routine host work
routine host SSH over the Proxmox Tailscale IP
ops@pam for routine Proxmox administration
lv3-automation@pve API token for durable Proxmox object management
short-lived `step-ca` SSH certificates accepted on the Proxmox host and managed guests
short-lived OpenBao AppRole artifacts refreshed on each converge and post-verification run
ops SSH + sudo for guest VMs
root key-only break-glass on the Proxmox host
root disabled for guest SSH
password SSH disabled on host and guests
```

## Control-plane lanes

<!-- BEGIN GENERATED: control-plane-lanes -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

### Lane Summary
| Lane | Title | Transport | Surfaces | Primary Rule |
| --- | --- | --- | --- | --- |
| `command` | Command Lane | `ssh` | 2 | Use SSH only for command-lane access. |
| `api` | API Lane | `https` | 16 | Default new APIs to internal-only or operator-only publication. |
| `message` | Message Lane | `authenticated_submission` | 2 | Submit platform mail through the internal mail platform rather than arbitrary external SMTP relays. |
| `event` | Event Lane | `mixed` | 16 | Event sinks must be documented and intentionally reachable. |

### API Publication Tiers
| Tier | Title | Surfaces | Summary |
| --- | --- | --- | --- |
| `internal-only` | Internal-Only | 20 | Reachable only from LV3 private networks, loopback paths, or explicitly trusted control-plane hosts. |
| `operator-only` | Operator-Only | 9 | Reachable only from approved operator devices over private access such as Tailscale. |
| `public-edge` | Public Edge | 3 | Intentionally published on a public domain through the named edge model. |
<!-- END GENERATED: control-plane-lanes -->


The generated lane summary above is the public-safe overview of the current control-plane model. Deeper deployment-specific operational details belong in runbooks, receipts, and fork-local overlays instead of the root README.

## Documents

<!-- BEGIN GENERATED: document-index -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

### Core Documents
- [Changelog](changelog.md)
- [Release notes](docs/release-notes/README.md)
- [Repository map](docs/repository-map.md)
- [Assistant operator guide](docs/assistant-operator-guide.md)
- [Release process](docs/release-process.md)
- [Workstreams registry](workstreams.yaml)
- [Workstreams guide](docs/workstreams/README.md)

### Discovery Indexes
- [ADR index](docs/adr/.index.yaml)
- [Runbooks directory](docs/runbooks)
- [Workstreams directory](docs/workstreams)
- [Release notes index](docs/release-notes/README.md)
- [Generated docs directory](docs/site-generated)
<!-- END GENERATED: document-index -->


## Versioning

- Repository version: [VERSION](VERSION)
- Desired platform and observed host state: [versions/stack.yaml](versions/stack.yaml)
- Versioning rules: [ADR 0008](docs/adr/0008-versioning-model-for-repo-and-host.md)
- Release notes index: [docs/release-notes/README.md](docs/release-notes/README.md)

Current values on `main`:

<!-- BEGIN GENERATED: version-summary -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

| Field | Value |
| --- | --- |
| Repository version | `0.178.2` |
| Platform version | `0.130.98` |
| Observed OS | `Debian 13` |
| Observed Proxmox installed | `true` |
| Observed PVE manager version | `9.1.6` |
| Declared services | 72 |
<!-- END GENERATED: version-summary -->

## Delivery Model

- ADRs remain the long-lived architecture truth
- active implementation is tracked in [workstreams.yaml](workstreams.yaml)
- each significant implementation stream gets a companion document under [docs/workstreams](docs/workstreams)
- branches and worktrees should stay easy to continue from another machine or fork
- version and release surfaces are reconciled on `main` during integration

## Merged Workstreams

<!-- BEGIN GENERATED: merged-workstreams -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

| ADR | Title | Status | Doc |
| --- | --- | --- | --- |
| `0011` | Monitoring stack rollout | `live_applied` | [adr-0011-monitoring.md](docs/workstreams/adr-0011-monitoring.md) |
| `0014` | Tailscale private access rollout | `live_applied` | [adr-0014-tailscale.md](docs/workstreams/adr-0014-tailscale.md) |
| `0020` | Initial storage and backup model | `merged` | [adr-0020-backups.md](docs/workstreams/adr-0020-backups.md) |
| `0021` | Repair shared edge certificate expansion during service-specific converges | `live_applied` | [ws-0021-edge-cert-repair.md](docs/workstreams/ws-0021-edge-cert-repair.md) |
| `0023` | Docker runtime VM baseline | `live_applied` | [adr-0023-docker-runtime.md](docs/workstreams/adr-0023-docker-runtime.md) |
| `0024` | Docker guest security baseline | `live_applied` | [adr-0024-docker-security.md](docs/workstreams/adr-0024-docker-security.md) |
| `0025` | Compose-managed runtime stacks | `merged` | [adr-0025-docker-compose-stacks.md](docs/workstreams/adr-0025-docker-compose-stacks.md) |
| `0026` | Dedicated PostgreSQL VM baseline | `merged` | [adr-0026-postgres-vm.md](docs/workstreams/adr-0026-postgres-vm.md) |
| `0027` | Uptime Kuma rollout on the Docker runtime VM | `merged` | [adr-0027-uptime-kuma.md](docs/workstreams/adr-0027-uptime-kuma.md) |
| `0028` | Docker build VM build count and duration telemetry | `live_applied` | [adr-0028-build-telemetry.md](docs/workstreams/adr-0028-build-telemetry.md) |
| `0029` | Dedicated backup VM with local PBS | `merged` | [adr-0029-backup-vm.md](docs/workstreams/adr-0029-backup-vm.md) |
| `0040` | Docker runtime container telemetry | `live_applied` | [adr-0040-runtime-container-telemetry.md](docs/workstreams/adr-0040-runtime-container-telemetry.md) |
| `0041` | Dockerized mail platform with API, Grafana telemetry, and failover delivery | `merged` | [adr-0041-email-platform.md](docs/workstreams/adr-0041-email-platform.md) |
| `0041` | Dockerized mail platform live rollout | `live_applied` | [adr-0041-email-platform-live.md](docs/workstreams/adr-0041-email-platform-live.md) |
| `0042` | step-ca for SSH and internal TLS | `live_applied` | [adr-0042-step-ca.md](docs/workstreams/adr-0042-step-ca.md) |
| `0043` | OpenBao for secrets, transit, and dynamic credentials | `live_applied` | [adr-0043-openbao.md](docs/workstreams/adr-0043-openbao.md) |
| `0044` | Windmill for agent and operator workflows | `live_applied` | [adr-0044-windmill.md](docs/workstreams/adr-0044-windmill.md) |
| `0045` | Control-plane communication lanes | `live_applied` | [adr-0045-communication-lanes.md](docs/workstreams/adr-0045-communication-lanes.md) |
| `0046` | Identity classes for humans, services, agents, and break-glass | `live_applied` | [adr-0046-identity-classes.md](docs/workstreams/adr-0046-identity-classes.md) |
| `0047` | Short-lived credentials and internal mTLS | `live_applied` | [adr-0047-short-lived-creds.md](docs/workstreams/adr-0047-short-lived-creds.md) |
| `0048` | Command catalog and approval gates | `live_applied` | [adr-0048-command-catalog.md](docs/workstreams/adr-0048-command-catalog.md) |
| `0049` | Private-first API publication model | `merged` | [adr-0049-private-api-publication.md](docs/workstreams/adr-0049-private-api-publication.md) |
| `0050` | Transactional email and notification profiles | `merged` | [adr-0050-notification-profiles.md](docs/workstreams/adr-0050-notification-profiles.md) |
| `0051` | Control-plane backup, recovery, and break-glass | `live_applied` | [adr-0051-control-plane-recovery.md](docs/workstreams/adr-0051-control-plane-recovery.md) |
| `0052` | Centralized log aggregation with Grafana Loki | `live_applied` | [adr-0052-loki-logs.md](docs/workstreams/adr-0052-loki-logs.md) |
| `0053` | OpenTelemetry traces and service maps with Grafana Tempo | `live_applied` | [adr-0053-tempo-traces.md](docs/workstreams/adr-0053-tempo-traces.md) |
| `0054` | NetBox for topology, IPAM, and inventory | `live_applied` | [adr-0054-netbox-topology.md](docs/workstreams/adr-0054-netbox-topology.md) |
| `0055` | Portainer for read-mostly Docker runtime operations | `live_applied` | [adr-0055-portainer-operations.md](docs/workstreams/adr-0055-portainer-operations.md) |
| `0056` | Keycloak for operator and agent SSO | `live_applied` | [adr-0056-keycloak-sso.md](docs/workstreams/adr-0056-keycloak-sso.md) |
| `0057` | Mattermost for ChatOps and operator-agent collaboration | `live_applied` | [adr-0057-mattermost-chatops.md](docs/workstreams/adr-0057-mattermost-chatops.md) |
| `0059` | ntopng for private network flow visibility | `live_applied` | [adr-0059-ntopng-network-visibility.md](docs/workstreams/adr-0059-ntopng-network-visibility.md) |
| `0060` | Open WebUI for operator and agent workbench | `live_applied` | [adr-0060-open-webui-workbench.md](docs/workstreams/adr-0060-open-webui-workbench.md) |
| `0062` | Ansible role composability and DRY defaults | `merged` | [adr-0062-role-composability.md](docs/workstreams/adr-0062-role-composability.md) |
| `0063` | Centralised vars and computed facts library | `merged` | [adr-0063-platform-vars-library.md](docs/workstreams/adr-0063-platform-vars-library.md) |
| `0064` | Health probe contracts for all services | `merged` | [adr-0064-health-probe-contracts.md](docs/workstreams/adr-0064-health-probe-contracts.md) |
| `0065` | Secret rotation automation with OpenBao | `live_applied` | [adr-0065-secret-rotation-automation.md](docs/workstreams/adr-0065-secret-rotation-automation.md) |
| `0067` | Guest network policy enforcement | `live_applied` | [adr-0067-guest-network-policy.md](docs/workstreams/adr-0067-guest-network-policy.md) |
| `0068` | Container image policy and supply chain integrity | `merged` | [adr-0068-container-image-policy.md](docs/workstreams/adr-0068-container-image-policy.md) |
| `0069` | Agent tool registry and governed tool calls | `merged` | [adr-0069-agent-tool-registry.md](docs/workstreams/adr-0069-agent-tool-registry.md) |
| `0070` | Retrieval-augmented context for platform queries | `live_applied` | [adr-0070-rag-platform-context.md](docs/workstreams/adr-0070-rag-platform-context.md) |
| `0071` | Agent observation loop and autonomous drift detection | `merged` | [adr-0071-agent-observation-loop.md](docs/workstreams/adr-0071-agent-observation-loop.md) |
| `0072` | Staging and production environment topology | `merged` | [adr-0072-staging-production-topology.md](docs/workstreams/adr-0072-staging-production-topology.md) |
| `0073` | Environment promotion gate and deployment pipeline | `merged` | [adr-0073-promotion-pipeline.md](docs/workstreams/adr-0073-promotion-pipeline.md) |
| `0074` | Platform operations portal | `live_applied` | [adr-0074-ops-portal.md](docs/workstreams/adr-0074-ops-portal.md) |
| `0075` | Service capability catalog | `merged` | [adr-0075-service-capability-catalog.md](docs/workstreams/adr-0075-service-capability-catalog.md) |
| `0076` | Subdomain governance and DNS lifecycle | `merged` | [adr-0076-subdomain-governance.md](docs/workstreams/adr-0076-subdomain-governance.md) |
| `0077` | Compose runtime secrets injection via OpenBao Agent | `live_applied` | [adr-0077-compose-secrets-injection.md](docs/workstreams/adr-0077-compose-secrets-injection.md) |
| `0078` | Service scaffold generator | `merged` | [adr-0078-service-scaffold.md](docs/workstreams/adr-0078-service-scaffold.md) |
| `0079` | Playbook decomposition and shared execution model | `merged` | [adr-0079-playbook-decomposition.md](docs/workstreams/adr-0079-playbook-decomposition.md) |
| `0080` | Maintenance window and change suppression protocol | `merged` | [adr-0080-maintenance-windows.md](docs/workstreams/adr-0080-maintenance-windows.md) |
| `0081` | Platform changelog and deployment history portal | `live_applied` | [adr-0081-changelog-portal.md](docs/workstreams/adr-0081-changelog-portal.md) |
| `0082` | Remote build execution gateway | `live_applied` | [adr-0082-remote-build-gateway.md](docs/workstreams/adr-0082-remote-build-gateway.md) |
| `0083` | Docker-based check runner | `merged` | [adr-0083-docker-check-runner.md](docs/workstreams/adr-0083-docker-check-runner.md) |
| `0084` | Packer VM template pipeline | `merged` | [adr-0084-packer-pipeline.md](docs/workstreams/adr-0084-packer-pipeline.md) |
| `0085` | Declarative VM provisioning with OpenTofu | `merged` | [adr-0085-opentofu-vm-lifecycle.md](docs/workstreams/adr-0085-opentofu-vm-lifecycle.md) |
| `0086` | Ansible collection packaging | `merged` | [adr-0086-ansible-collections.md](docs/workstreams/adr-0086-ansible-collections.md) |
| `0087` | Repository validation gate | `merged` | [adr-0087-validation-gate.md](docs/workstreams/adr-0087-validation-gate.md) |
| `0088` | Ephemeral infrastructure fixtures | `merged` | [adr-0088-ephemeral-fixtures.md](docs/workstreams/adr-0088-ephemeral-fixtures.md) |
| `0089` | Build artifact cache and layer registry | `merged` | [adr-0089-build-cache.md](docs/workstreams/adr-0089-build-cache.md) |
| `0090` | Unified platform CLI | `merged` | [adr-0090-platform-cli.md](docs/workstreams/adr-0090-platform-cli.md) |
| `0091` | Continuous drift detection and reconciliation | `merged` | [adr-0091-drift-detection.md](docs/workstreams/adr-0091-drift-detection.md) |
| `0092` | Unified platform API gateway | `live_applied` | [adr-0092-platform-api-gateway.md](docs/workstreams/adr-0092-platform-api-gateway.md) |
| `0093` | Interactive ops portal with live actions | `live_applied` | [adr-0093-interactive-ops-portal.md](docs/workstreams/adr-0093-interactive-ops-portal.md) |
| `0094` | Developer portal and service documentation site | `live_applied` | [adr-0094-developer-portal.md](docs/workstreams/adr-0094-developer-portal.md) |
| `0096` | SLO definitions and error budget tracking | `live_applied` | [adr-0096-slo-tracking.md](docs/workstreams/adr-0096-slo-tracking.md) |
| `0097` | Alerting routing and on-call runbook model | `merged` | [adr-0097-alerting-routing.md](docs/workstreams/adr-0097-alerting-routing.md) |
| `0098` | Postgres high availability and automated failover | `merged` | [adr-0098-postgres-ha.md](docs/workstreams/adr-0098-postgres-ha.md) |
| `0099` | Automated backup restore verification | `merged` | [adr-0099-backup-restore-verification.md](docs/workstreams/adr-0099-backup-restore-verification.md) |
| `0100` | RTO/RPO targets and disaster recovery playbook | `merged` | [adr-0100-disaster-recovery-playbook.md](docs/workstreams/adr-0100-disaster-recovery-playbook.md) |
| `0101` | Automated certificate lifecycle management | `live_applied` | [adr-0101-certificate-lifecycle.md](docs/workstreams/adr-0101-certificate-lifecycle.md) |
| `0101` | ADR 0101 live apply from latest origin/main | `live_applied` | [ws-0101-live-apply.md](docs/workstreams/ws-0101-live-apply.md) |
| `0102` | Security posture reporting and benchmark drift | `merged` | [adr-0102-security-posture-reporting.md](docs/workstreams/adr-0102-security-posture-reporting.md) |
| `0103` | Data classification and retention policy | `merged` | [adr-0103-data-retention-policy.md](docs/workstreams/adr-0103-data-retention-policy.md) |
| `0104` | Service dependency graph and failure propagation model | `merged` | [adr-0104-dependency-graph.md](docs/workstreams/adr-0104-dependency-graph.md) |
| `0105` | Platform capacity model and resource quota enforcement | `merged` | [adr-0105-capacity-model.md](docs/workstreams/adr-0105-capacity-model.md) |
| `0105` | ADR 0105 live apply from latest origin/main | `merged` | [ws-0105-live-apply.md](docs/workstreams/ws-0105-live-apply.md) |
| `0106` | Ephemeral environment lifecycle and teardown policy | `merged` | [adr-0106-ephemeral-lifecycle.md](docs/workstreams/adr-0106-ephemeral-lifecycle.md) |
| `0107` | Platform extension model for adding new services | `merged` | [adr-0107-extension-model.md](docs/workstreams/adr-0107-extension-model.md) |
| `0108` | Operator onboarding and off-boarding workflow | `live_applied` | [adr-0108-operator-onboarding.md](docs/workstreams/adr-0108-operator-onboarding.md) |
| `0108` | Operator onboarding and off-boarding live apply | `live_applied` | [ws-0108-live-apply.md](docs/workstreams/ws-0108-live-apply.md) |
| `0109` | Public status page | `merged` | [adr-0109-public-status-page.md](docs/workstreams/adr-0109-public-status-page.md) |
| `0110` | Platform versioning, release notes, and upgrade path | `merged` | [adr-0110-platform-versioning.md](docs/workstreams/adr-0110-platform-versioning.md) |
| `0111` | End-to-end integration test suite | `merged` | [adr-0111-integration-test-suite.md](docs/workstreams/adr-0111-integration-test-suite.md) |
| `0112` | Deterministic goal compiler | `merged` | [adr-0112-goal-compiler.md](docs/workstreams/adr-0112-goal-compiler.md) |
| `0113` | World-state materializer | `live_applied` | [adr-0113-world-state-materializer.md](docs/workstreams/adr-0113-world-state-materializer.md) |
| `0114` | Rule-based incident triage engine | `merged` | [adr-0114-incident-triage-engine.md](docs/workstreams/adr-0114-incident-triage-engine.md) |
| `0115` | Event-sourced mutation ledger | `merged` | [adr-0115-mutation-ledger.md](docs/workstreams/adr-0115-mutation-ledger.md) |
| `0116` | Deterministic workflow change risk scoring | `merged` | [adr-0116-change-risk-scoring.md](docs/workstreams/adr-0116-change-risk-scoring.md) |
| `0117` | Service dependency graph as first-class runtime | `live_applied` | [adr-0117-dependency-graph-runtime.md](docs/workstreams/adr-0117-dependency-graph-runtime.md) |
| `0119` | Budgeted workflow scheduler | `live_applied` | [adr-0119-budgeted-workflow-scheduler.md](docs/workstreams/adr-0119-budgeted-workflow-scheduler.md) |
| `0120` | Dry-run semantic diff engine | `merged` | [adr-0120-dry-run-diff-engine.md](docs/workstreams/adr-0120-dry-run-diff-engine.md) |
| `0121` | Local search and indexing fabric | `merged` | [adr-0121-search-indexing-fabric.md](docs/workstreams/adr-0121-search-indexing-fabric.md) |
| `0122` | Windmill operator access admin surface | `live_applied` | [adr-0122-operator-access-admin.md](docs/workstreams/adr-0122-operator-access-admin.md) |
| `0123` | Service uptime contracts and monitor-backed health | `merged` | [adr-0123-service-uptime-contracts.md](docs/workstreams/adr-0123-service-uptime-contracts.md) |
| `0124` | Platform event taxonomy and canonical NATS topics | `live_applied` | [adr-0124-platform-event-taxonomy.md](docs/workstreams/adr-0124-platform-event-taxonomy.md) |
| `0125` | Agent capability bounds and autonomous action policy | `merged` | [adr-0125-agent-capability-bounds.md](docs/workstreams/adr-0125-agent-capability-bounds.md) |
| `0126` | Observation-to-action closure loop | `live_applied` | [adr-0126-observation-to-action-closure-loop.md](docs/workstreams/adr-0126-observation-to-action-closure-loop.md) |
| `0127` | Intent deduplication and conflict resolution | `merged` | [adr-0127-intent-conflict-resolution.md](docs/workstreams/adr-0127-intent-conflict-resolution.md) |
| `0128` | Platform health composite index | `merged` | [adr-0128-platform-health-composite-index.md](docs/workstreams/adr-0128-platform-health-composite-index.md) |
| `0129` | Runbook automation executor | `merged` | [adr-0129-runbook-automation-executor.md](docs/workstreams/adr-0129-runbook-automation-executor.md) |
| `0130` | Agent state persistence across workflow boundaries | `merged` | [adr-0130-agent-state-persistence.md](docs/workstreams/adr-0130-agent-state-persistence.md) |
| `0131` | Multi-agent handoff protocol | `merged` | [adr-0131-agent-handoff-protocol.md](docs/workstreams/adr-0131-agent-handoff-protocol.md) |
| `0132` | Self-describing platform manifest | `merged` | [adr-0132-self-describing-platform-manifest.md](docs/workstreams/adr-0132-self-describing-platform-manifest.md) |
| `0133` | Portal authentication by default | `merged` | [adr-0133-portal-authentication-by-default.md](docs/workstreams/adr-0133-portal-authentication-by-default.md) |
| `0134` | Changelog portal content redaction | `merged` | [adr-0134-changelog-redaction.md](docs/workstreams/adr-0134-changelog-redaction.md) |
| `0135` | Developer portal sensitivity classification | `merged` | [adr-0135-developer-portal-sensitivity-classification.md](docs/workstreams/adr-0135-developer-portal-sensitivity-classification.md) |
| `0136` | HTTP security headers hardening | `live_applied` | [adr-0136-http-security-headers.md](docs/workstreams/adr-0136-http-security-headers.md) |
| `0137` | Robots.txt and crawl policy | `live_applied` | [adr-0137-robots-and-crawl-policy.md](docs/workstreams/adr-0137-robots-and-crawl-policy.md) |
| `0138` | Published artifact secret scanning | `live_applied` | [adr-0138-published-artifact-secret-scanning.md](docs/workstreams/adr-0138-published-artifact-secret-scanning.md) |
| `0139` | Subdomain exposure audit and registry | `merged` | [adr-0139-subdomain-exposure-audit.md](docs/workstreams/adr-0139-subdomain-exposure-audit.md) |
| `0140` | Grafana public access hardening | `live_applied` | [adr-0140-grafana-public-access-hardening.md](docs/workstreams/adr-0140-grafana-public-access-hardening.md) |
| `0141` | API token lifecycle and exposure response | `merged` | [adr-0141-api-token-lifecycle.md](docs/workstreams/adr-0141-api-token-lifecycle.md) |
| `0142` | Public surface automated security scan | `merged` | [adr-0142-public-surface-security-scan.md](docs/workstreams/adr-0142-public-surface-security-scan.md) |
| `0143` | Private Gitea with self-hosted CI | `merged` | [adr-0143-gitea-ci.md](docs/workstreams/adr-0143-gitea-ci.md) |
| `0144` | Headscale mesh control plane | `merged` | [adr-0144-headscale.md](docs/workstreams/adr-0144-headscale.md) |
| `0145` | Ollama for local LLM inference | `live_applied` | [adr-0145-ollama.md](docs/workstreams/adr-0145-ollama.md) |
| `0146` | Langfuse for agent observability | `live_applied` | [adr-0146-ai-observability.md](docs/workstreams/adr-0146-ai-observability.md) |
| `0147` | Vaultwarden for operator credential management | `live_applied` | [adr-0147-vaultwarden.md](docs/workstreams/adr-0147-vaultwarden.md) |
| `0148` | SearXNG for agent web search | `merged` | [adr-0148-searxng-web-search.md](docs/workstreams/adr-0148-searxng-web-search.md) |
| `0150` | Dozzle for real-time container log access | `live_applied` | [adr-0150-dozzle.md](docs/workstreams/adr-0150-dozzle.md) |
| `0151` | n8n for webhook and API integration automation | `live_applied` | [adr-0151-n8n.md](docs/workstreams/adr-0151-n8n.md) |
| `0152` | Homepage for unified service dashboard | `live_applied` | [adr-0152-homepage.md](docs/workstreams/adr-0152-homepage.md) |
| `0152` | Triage failing Homepage services and restore safe runtime health | `live_applied` | [ws-0332-homepage-triage.md](docs/workstreams/ws-0332-homepage-triage.md) |
| `0153` | Distributed resource lock registry | `merged` | [adr-0153-distributed-resource-lock-registry.md](docs/workstreams/adr-0153-distributed-resource-lock-registry.md) |
| `0154` | VM-scoped parallel execution lanes | `live_applied` | [adr-0154-vm-scoped-execution-lanes.md](docs/workstreams/adr-0154-vm-scoped-execution-lanes.md) |
| `0155` | Intent queue with release-triggered scheduling | `live_applied` | [adr-0155-intent-queue-with-release-triggered-scheduling.md](docs/workstreams/adr-0155-intent-queue-with-release-triggered-scheduling.md) |
| `0156` | Agent session workspace isolation | `live_applied` | [adr-0156-agent-session-workspace-isolation.md](docs/workstreams/adr-0156-agent-session-workspace-isolation.md) |
| `0157` | Per-VM concurrency budget and resource reservation | `live_applied` | [adr-0157-per-vm-concurrency-budget.md](docs/workstreams/adr-0157-per-vm-concurrency-budget.md) |
| `0158` | Conflict-free configuration merge protocol | `live_applied` | [adr-0158-config-merge-protocol.md](docs/workstreams/adr-0158-config-merge-protocol.md) |
| `0159` | Speculative parallel execution with compensating transactions | `merged` | [adr-0159-speculative-parallel-execution.md](docs/workstreams/adr-0159-speculative-parallel-execution.md) |
| `0160` | Parallel dry-run fan-out for intent batch validation | `merged` | [adr-0160-parallel-dry-run-fan-out.md](docs/workstreams/adr-0160-parallel-dry-run-fan-out.md) |
| `0161` | Real-time agent coordination map | `live_applied` | [adr-0161-real-time-agent-coordination-map.md](docs/workstreams/adr-0161-real-time-agent-coordination-map.md) |
| `0162` | Distributed deadlock detection and resolution | `live_applied` | [adr-0162-deadlock-detector.md](docs/workstreams/adr-0162-deadlock-detector.md) |
| `0163` | Platform-wide retry taxonomy and exponential backoff | `live_applied` | [adr-0163-retry-taxonomy.md](docs/workstreams/adr-0163-retry-taxonomy.md) |
| `0164` | Circuit breaker pattern for external service calls | `live_applied` | [adr-0164-circuit-breaker-pattern.md](docs/workstreams/adr-0164-circuit-breaker-pattern.md) |
| `0165` | Workflow idempotency keys and double-execution prevention | `live_applied` | [adr-0165-workflow-idempotency.md](docs/workstreams/adr-0165-workflow-idempotency.md) |
| `0166` | Canonical error response format and error code registry | `live_applied` | [adr-0166-canonical-error-response-format.md](docs/workstreams/adr-0166-canonical-error-response-format.md) |
| `0167` | Graceful degradation mode declarations | `live_applied` | [adr-0167-graceful-degradation-mode-declarations.md](docs/workstreams/adr-0167-graceful-degradation-mode-declarations.md) |
| `0168` | Ansible role idempotency CI enforcement | `merged` | [adr-0168-idempotency-ci.md](docs/workstreams/adr-0168-idempotency-ci.md) |
| `0169` | Structured log field contract | `live_applied` | [adr-0169-structured-log-field-contract.md](docs/workstreams/adr-0169-structured-log-field-contract.md) |
| `0170` | Platform-wide timeout hierarchy | `live_applied` | [adr-0170-timeout-hierarchy.md](docs/workstreams/adr-0170-timeout-hierarchy.md) |
| `0171` | Controlled fault injection for resilience validation | `live_applied` | [adr-0171-controlled-fault-injection.md](docs/workstreams/adr-0171-controlled-fault-injection.md) |
| `0172` | Watchdog escalation and stale job self-healing | `merged` | [adr-0172-watchdog-escalation-and-stale-job-self-healing.md](docs/workstreams/adr-0172-watchdog-escalation-and-stale-job-self-healing.md) |
| `0173` | Workstream surface ownership manifest | `live_applied` | [adr-0173-workstream-surface-ownership-manifest.md](docs/workstreams/adr-0173-workstream-surface-ownership-manifest.md) |
| `0174` | Integration-only canonical truth assembly | `merged` | [adr-0174-canonical-truth-assembly.md](docs/workstreams/adr-0174-canonical-truth-assembly.md) |
| `0175` | Cross-workstream interface contracts | `merged` | [adr-0175-cross-workstream-interface-contracts.md](docs/workstreams/adr-0175-cross-workstream-interface-contracts.md) |
| `0176` | Inventory sharding and host-scoped Ansible execution | `live_applied` | [adr-0176-inventory-sharding.md](docs/workstreams/adr-0176-inventory-sharding.md) |
| `0177` | Run namespace partitioning for parallel tooling | `merged` | [adr-0177-run-namespace-partitioning.md](docs/workstreams/adr-0177-run-namespace-partitioning.md) |
| `0178` | Dependency wave manifests for parallel apply | `merged` | [adr-0178-dependency-wave-manifests.md](docs/workstreams/adr-0178-dependency-wave-manifests.md) |
| `0179` | Service redundancy tier matrix | `merged` | [adr-0179-service-redundancy-tier-matrix.md](docs/workstreams/adr-0179-service-redundancy-tier-matrix.md) |
| `0181` | Off-host witness and control metadata replication | `live_applied` | [adr-0181-off-host-witness-replication.md](docs/workstreams/adr-0181-off-host-witness-replication.md) |
| `0182` | Live apply merge train and rollback bundle | `merged` | [adr-0182-live-apply-merge-train-and-rollback-bundle.md](docs/workstreams/adr-0182-live-apply-merge-train-and-rollback-bundle.md) |
| `0183` | Multi-environment live lanes | `live_applied` | [adr-0183-multi-environment-live-lanes.md](docs/workstreams/adr-0183-multi-environment-live-lanes.md) |
| `0184` | Failure-domain labels and anti-affinity policy live apply | `live_applied` | [ws-0184-live-apply.md](docs/workstreams/ws-0184-live-apply.md) |
| `0185` | Branch-scoped ephemeral preview environments | `merged` | [adr-0185-branch-scoped-ephemeral-preview-environments.md](.worktrees/ws-0185-live-apply/docs/workstreams/adr-0185-branch-scoped-ephemeral-preview-environments.md) |
| `0186` | Live apply ADR 0186 prewarmed fixture pools and lease-based ephemeral capacity | `merged` | [ws-0186-live-apply.md](docs/workstreams/ws-0186-live-apply.md) |
| `0187` | ADR 0187 live apply from latest origin/main | `live_applied` | [ws-0187-live-apply.md](docs/workstreams/ws-0187-live-apply.md) |
| `0188` | Failover rehearsal gate live apply | `live_applied` | [ws-0188-live-apply.md](../worktree-ws-0188-live-apply/docs/workstreams/ws-0188-live-apply.md) |
| `0189` | ADR 0189 live apply from latest origin/main | `live_applied` | [ws-0189-live-apply.md](docs/workstreams/ws-0189-live-apply.md) |
| `0190` | ADR 0190 live apply from latest origin/main | `merged` | [ws-0190-live-apply.md](docs/workstreams/ws-0190-live-apply.md) |
| `0191` | Immutable guest replacement for stateful and edge services | `live_applied` | [ws-0191-live-apply.md](docs/workstreams/ws-0191-live-apply.md) |
| `0192` | Live apply ADR 0192 capacity classes for standby, recovery, and preview workloads | `merged` | [ws-0192-live-apply.md](docs/workstreams/ws-0192-live-apply.md) |
| `0193` | Plane Kanban Task Board | `merged` | [adr-0193-plane-kanban-task-board.md](docs/workstreams/adr-0193-plane-kanban-task-board.md) |
| `0193` | Integrate ADR 0193 live apply into origin/main | `live_applied` | [ws-0193-main-merge.md](docs/workstreams/ws-0193-main-merge.md) |
| `0194` | Coolify PaaS deploy from repo | `merged` | [adr-0194-coolify-paas-deploy-from-repo.md](docs/workstreams/adr-0194-coolify-paas-deploy-from-repo.md) |
| `0194` | Integrate ADR 0194 live apply into origin/main | `merged` | [ws-0194-main-merge.md](docs/workstreams/ws-0194-main-merge.md) |
| `0196` | ADR 0196 live apply from latest origin/main | `merged` | [ws-0196-live-apply.md](docs/workstreams/ws-0196-live-apply.md) |
| `0199` | Outline living knowledge wiki | `merged` | [adr-0199-outline-living-knowledge-wiki.md](.worktrees/ws-0199-live-apply/docs/workstreams/adr-0199-outline-living-knowledge-wiki.md) |
| `0201` | Harbor runtime deployment, registry cutover, and repository automation replay | `live_applied` | [ws-0201-live-apply.md](docs/workstreams/ws-0201-live-apply.md) |
| `0201` | Finalize ADR 0201 Harbor exact-main evidence on origin/main | `merged` | [ws-0201-main-merge.md](docs/workstreams/ws-0201-main-merge.md) |
| `0202` | Excalidraw auto generated architecture diagrams | `live_applied` | [adr-0202-excalidraw-auto-generated-architecture-diagrams.md](docs/workstreams/adr-0202-excalidraw-auto-generated-architecture-diagrams.md) |
| `0204` | Architecture governance bundle for self-correction, clean boundaries, and vendor replaceability | `merged` | [adr-0204-architecture-governance.md](docs/workstreams/adr-0204-architecture-governance.md) |
| `0204` | Self-correcting automation loops live apply | `merged` | [ws-0204-live-apply.md](docs/workstreams/ws-0204-live-apply.md) |
| `0206` | Live apply ADR 0206 ports and adapters for external integrations | `live_applied` | [ws-0206-live-apply.md](docs/workstreams/ws-0206-live-apply.md) |
| `0206` | Integrate ADR 0206 live apply into origin/main | `merged` | [ws-0206-main-merge.md](docs/workstreams/ws-0206-main-merge.md) |
| `0209` | Shared runbook use-case service with thin CLI, API gateway, Windmill, and ops portal adapters | `live_applied` | [ws-0209-live-apply.md](docs/workstreams/ws-0209-live-apply.md) |
| `0210` | Live apply canonical publication models over adapter-shaped vendor fields | `merged` | [ws-0210-live-apply.md](docs/workstreams/ws-0210-live-apply.md) |
| `0211` | Shared policy packs and rule registries live apply | `merged` | [adr-0211-shared-policy-packs-and-rule-registries.md](docs/workstreams/adr-0211-shared-policy-packs-and-rule-registries.md) |
| `0211` | Integrate ADR 0211 shared policy registries into origin/main | `merged` | [ws-0211-main-merge.md](docs/workstreams/ws-0211-main-merge.md) |
| `0212` | Replaceability scorecards and vendor exit plans live apply | `merged` | [ws-0212-live-apply.md](docs/workstreams/ws-0212-live-apply.md) |
| `0214` | HA and replication architecture bundle for production and staging | `merged` | [adr-0214-ha-replication-architecture-bundle.md](docs/workstreams/adr-0214-ha-replication-architecture-bundle.md) |
| `0224` | Live apply ADR 0224 server-resident operations as the default control model | `live_applied` | [ws-0224-live-apply.md](docs/workstreams/ws-0224-live-apply.md) |
| `0224` | Server-resident operations architecture bundle | `merged` | [adr-0224-server-resident-operations-architecture-bundle.md](docs/workstreams/adr-0224-server-resident-operations-architecture-bundle.md) |
| `0224` | Refresh education_wemeshup from upstream main through a named repo-deploy profile | `merged` | [ws-0296-education-refresh.md](docs/workstreams/ws-0296-education-refresh.md) |
| `0226` | Live apply ADR 0226 systemd host-resident control-loop supervision | `live_applied` | [ws-0226-live-apply.md](docs/workstreams/ws-0226-live-apply.md) |
| `0226` | Finalize ADR 0226 exact-main evidence on origin/main | `merged` | [ws-0226-main-merge.md](docs/workstreams/ws-0226-main-merge.md) |
| `0228` | Integrate ADR 0228 live apply into origin/main | `live_applied` | [ws-0228-main-merge.md](docs/workstreams/ws-0228-main-merge.md) |
| `0230` | Live apply policy decisions via Open Policy Agent and Conftest | `live_applied` | [ws-0230-live-apply.md](docs/workstreams/ws-0230-live-apply.md) |
| `0231` | Live apply ADR 0231 local secret delivery via OpenBao Agent and systemd credentials | `live_applied` | [ws-0231-live-apply.md](docs/workstreams/ws-0231-live-apply.md) |
| `0231` | Integrate ADR 0231 live apply into origin/main | `merged` | [ws-0231-main-merge.md](docs/workstreams/ws-0231-main-merge.md) |
| `0232` | Live apply and verify the private Nomad scheduler | `live_applied` | [ws-0232-live-apply.md](docs/workstreams/ws-0232-live-apply.md) |
| `0232` | Integrate ADR 0232 live apply into origin/main | `merged` | [ws-0232-main-merge.md](docs/workstreams/ws-0232-main-merge.md) |
| `0233` | Live apply signed release bundles via Gitea Releases and Cosign | `live_applied` | [ws-0233-live-apply.md](docs/workstreams/ws-0233-live-apply.md) |
| `0233` | Integrate ADR 0233 signed release bundles into origin/main | `merged` | [ws-0233-main-merge.md](docs/workstreams/ws-0233-main-merge.md) |
| `0234` | Human user experience architecture bundle | `merged` | [adr-0234-human-user-experience-architecture-bundle.md](docs/workstreams/adr-0234-human-user-experience-architecture-bundle.md) |
| `0234` | Live apply shared human app shell and navigation via PatternFly | `live_applied` | [ws-0234-live-apply.md](docs/workstreams/ws-0234-live-apply.md) |
| `0235` | Live apply cross-application launcher and favorites in the interactive ops portal | `live_applied` | [ws-0235-live-apply.md](docs/workstreams/ws-0235-live-apply.md) |
| `0235` | Integrate ADR 0235 cross-application launcher into origin/main | `merged` | [ws-0235-main-merge.md](docs/workstreams/ws-0235-main-merge.md) |
| `0236` | Live apply TanStack Query server-state conventions on the Windmill operator admin app | `live_applied` | [ws-0236-live-apply.md](docs/workstreams/ws-0236-live-apply.md) |
| `0236` | Integrate ADR 0236 TanStack Query server-state feedback into origin/main | `merged` | [ws-0236-main-merge.md](docs/workstreams/ws-0236-main-merge.md) |
| `0237` | Live apply schema-first human forms via React Hook Form and Zod | `live_applied` | [ws-0237-live-apply.md](docs/workstreams/ws-0237-live-apply.md) |
| `0237` | Integrate ADR 0237 schema-first human forms into origin/main | `merged` | [ws-0237-main-merge.md](docs/workstreams/ws-0237-main-merge.md) |
| `0238` | Data-dense operator grids live apply | `live_applied` | [ws-0238-live-apply.md](docs/workstreams/ws-0238-live-apply.md) |
| `0238` | Integrate ADR 0238 operator grid into origin/main | `merged` | [ws-0238-main-integration.md](docs/workstreams/ws-0238-main-integration.md) |
| `0239` | Live apply browser-local search experience via Pagefind | `live_applied` | [ws-0239-live-apply.md](docs/workstreams/ws-0239-live-apply.md) |
| `0239` | Integrate ADR 0239 browser-local search into origin/main | `merged` | [ws-0239-main-merge.md](docs/workstreams/ws-0239-main-merge.md) |
| `0240` | Live apply operator visualization panels via Apache ECharts | `live_applied` | [ws-0240-live-apply.md](docs/workstreams/ws-0240-live-apply.md) |
| `0240` | Integrate ADR 0240 operator visualization panels into origin/main | `merged` | [ws-0240-main-merge.md](docs/workstreams/ws-0240-main-merge.md) |
| `0241` | Live apply ADR 0241 rich content and inline knowledge editing via Tiptap | `live_applied` | [ws-0241-live-apply.md](docs/workstreams/ws-0241-live-apply.md) |
| `0241` | Integrate ADR 0241 rich content and inline knowledge editing into origin/main | `merged` | [ws-0241-main-merge.md](docs/workstreams/ws-0241-main-merge.md) |
| `0242` | Guided human onboarding live apply via Shepherd tours | `live_applied` | [ws-0242-live-apply.md](docs/workstreams/ws-0242-live-apply.md) |
| `0242` | Integrate ADR 0242 guided onboarding into origin/main | `merged` | [ws-0242-main-merge.md](docs/workstreams/ws-0242-main-merge.md) |
| `0244` | Live apply runtime assurance matrix per service and environment | `live_applied` | [ws-0244-live-apply.md](docs/workstreams/ws-0244-live-apply.md) |
| `0244` | Integrate ADR 0244 runtime assurance matrix into origin/main | `merged` | [ws-0244-main-merge.md](docs/workstreams/ws-0244-main-merge.md) |
| `0244` | Runtime assurance architecture bundle | `merged` | [adr-0244-runtime-assurance-architecture-bundle.md](docs/workstreams/adr-0244-runtime-assurance-architecture-bundle.md) |
| `0245` | Declared-to-live service attestation live apply | `live_applied` | [ws-0245-live-apply.md](docs/workstreams/ws-0245-live-apply.md) |
| `0246` | Live apply startup, readiness, liveness, and degraded-state semantics | `live_applied` | [ws-0246-live-apply.md](docs/workstreams/ws-0246-live-apply.md) |
| `0246` | Integrate ADR 0246 runtime-state semantics into origin/main | `merged` | [ws-0246-main-merge.md](docs/workstreams/ws-0246-main-merge.md) |
| `0248` | Live apply session and logout authority across Keycloak, oauth2-proxy, and app surfaces | `live_applied` | [ws-0248-live-apply.md](docs/workstreams/ws-0248-live-apply.md) |
| `0248` | Integrate ADR 0248 session/logout authority into origin/main | `merged` | [ws-0248-main-merge.md](docs/workstreams/ws-0248-main-merge.md) |
| `0249` | Live apply HTTPS and TLS assurance through blackbox exporter and testssl.sh | `live_applied` | [ws-0249-live-apply.md](docs/workstreams/ws-0249-live-apply.md) |
| `0250` | ADR 0250 live apply from latest origin/main | `live_applied` | [ws-0250-live-apply.md](docs/workstreams/ws-0250-live-apply.md) |
| `0251` | Live apply stage-scoped smoke suites and promotion gates | `live_applied` | [ws-0251-live-apply.md](docs/workstreams/ws-0251-live-apply.md) |
| `0251` | Stage-scoped smoke suites and promotion-gate live apply | `live_applied` | [ws-0251-live-apply-r2.md](docs/workstreams/ws-0251-live-apply-r2.md) |
| `0251` | Integrate ADR 0251 exact-main durable verification onto current origin/main | `merged` | [ws-0251-main-integration.md](docs/workstreams/ws-0251-main-integration.md) |
| `0252` | Live apply ADR 0252 route and DNS publication assertion ledger | `live_applied` | [ws-0252-live-apply.md](docs/workstreams/ws-0252-live-apply.md) |
| `0252` | Integrate ADR 0252 exact-main replay onto current origin/main | `merged` | [ws-0252-main-merge.md](docs/workstreams/ws-0252-main-merge.md) |
| `0252` | Re-verify ADR 0252 from the latest origin/main and prepare final merge surfaces | `live_applied` | [ws-0252-mainline-replay.md](docs/workstreams/ws-0252-mainline-replay.md) |
| `0253` | Unified runtime assurance scoreboard live apply | `live_applied` | [ws-0253-live-apply.md](docs/workstreams/ws-0253-live-apply.md) |
| `0254` | ServerClaw architecture bundle | `merged` | [adr-0254-serverclaw-architecture-bundle.md](docs/workstreams/adr-0254-serverclaw-architecture-bundle.md) |
| `0255` | ADR 0255 live apply from latest origin/main | `live_applied` | [ws-0255-live-apply.md](docs/workstreams/ws-0255-live-apply.md) |
| `0255` | Integrate ADR 0255 exact-main replay onto current origin/main | `merged` | [ws-0255-main-integration.md](docs/workstreams/ws-0255-main-integration.md) |
| `0259` | Live apply n8n as the external app connector fabric for ServerClaw | `live_applied` | [ws-0259-live-apply.md](docs/workstreams/ws-0259-live-apply.md) |
| `0259` | Integrate ADR 0259 exact-main replay onto current origin/main | `merged` | [ws-0259-main-merge.md](docs/workstreams/ws-0259-main-merge.md) |
| `0264` | Failure-domain-isolated validation lanes live apply | `live_applied` | [ws-0264-live-apply.md](docs/workstreams/ws-0264-live-apply.md) |
| `0264` | Integrate ADR 0264 failure-domain-isolated validation lanes onto origin/main | `merged` | [ws-0264-main-merge.md](docs/workstreams/ws-0264-main-merge.md) |
| `0264` | Receipt-driven resilience architecture bundle | `merged` | [adr-0264-receipt-driven-resilience-architecture-bundle.md](docs/workstreams/adr-0264-receipt-driven-resilience-architecture-bundle.md) |
| `0265` | Immutable validation snapshots for remote builders and schema checks | `live_applied` | [adr-0265-immutable-validation-snapshots-for-remote-builders-and-schema-checks.md](docs/workstreams/adr-0265-immutable-validation-snapshots-for-remote-builders-and-schema-checks.md) |
| `0266` | Validation runner capability contracts and environment attestation | `live_applied` | [adr-0266-validation-runner-capability-contracts-live-apply.md](docs/workstreams/adr-0266-validation-runner-capability-contracts-live-apply.md) |
| `0268` | Fresh-worktree bootstrap manifests live apply | `live_applied` | [ws-0268-live-apply.md](docs/workstreams/ws-0268-live-apply.md) |
| `0268` | Integrate ADR 0268 exact-main replay onto current origin/main | `merged` | [ws-0268-main-integration.md](docs/workstreams/ws-0268-main-integration.md) |
| `0271` | Backup coverage assertion ledger live apply | `live_applied` | [ws-0271-live-apply.md](docs/workstreams/ws-0271-live-apply.md) |
| `0272` | Restore readiness ladders and stateful warm-up verification profiles | `live_applied` | [ws-0272-live-apply.md](docs/workstreams/ws-0272-live-apply.md) |
| `0273` | Live apply ADR 0273 public endpoint admission control | `live_applied` | [adr-0273-public-endpoint-admission-control.md](docs/workstreams/adr-0273-public-endpoint-admission-control.md) |
| `0274` | Live apply ADR 0274 shared MinIO object storage from latest origin/main | `live_applied` | [ws-0274-minio-live-apply.md](docs/workstreams/ws-0274-minio-live-apply.md) |
| `0277` | Live apply the private Typesense structured-search plane from latest origin/main | `live_applied` | [ws-0277-live-apply.md](docs/workstreams/ws-0277-live-apply.md) |
| `0279` | Integrate ADR 0279 exact-main replay onto current origin/main | `live_applied` | [ws-0279-main-merge.md](docs/workstreams/ws-0279-main-merge.md) |
| `0281` | Live apply the GlitchTip application error tracking stack from latest origin/main | `live_applied` | [ws-0281-live-apply.md](docs/workstreams/ws-0281-live-apply.md) |
| `0289` | Live apply ADR 0289 Label Studio from latest origin/main | `live_applied` | [ws-0289-label-studio-live-apply.md](docs/workstreams/ws-0289-label-studio-live-apply.md) |
| `0292` | Live apply Lago as the usage metering and billing API layer from latest origin/main | `merged` | [ws-0292-live-apply.md](docs/workstreams/ws-0292-live-apply.md) |
| `0292` | Live apply ADR 0292 Apache Superset from latest origin/main | `live_applied` | [ws-0292-superset-live-apply.md](docs/workstreams/ws-0292-superset-live-apply.md) |
| `0293` | Live apply LiveKit as the real-time audio and voice channel for agents from latest origin/main | `live_applied` | [ws-0293-livekit-live-apply.md](docs/workstreams/ws-0293-livekit-live-apply.md) |
| `0293` | Integrate ADR 0293 exact-main LiveKit replay onto main | `merged` | [ws-0293-main-integration.md](docs/workstreams/ws-0293-main-integration.md) |
| `0294` | Live apply One-API as the unified LLM API proxy and router from latest origin/main | `live_applied` | [ws-0294-live-apply.md](docs/workstreams/ws-0294-live-apply.md) |
| `0295` | Shared artifact cache plane and dedicated cache VM roadmap | `live_applied` | [adr-0295-artifact-cache-architecture-bundle.md](docs/workstreams/adr-0295-artifact-cache-architecture-bundle.md) |
| `0295` | Live apply the shared artifact cache plane from latest origin/main | `live_applied` | [ws-0295-live-apply.md](docs/workstreams/ws-0295-live-apply.md) |
| `0297` | Live apply Renovate as the automated stack version upgrade proposer from latest origin/main | `merged` | [ws-0297-live-apply.md](docs/workstreams/ws-0297-live-apply.md) |
| `0297` | Integrate ADR 0297 live-apply evidence and release updates on main | `merged` | [ws-0297-main-merge.md](docs/workstreams/ws-0297-main-merge.md) |
| `0297` | Resolve Gitea release bundle retention and Renovate PR validation checkout drift | `live_applied` | [ws-0315-gitea-followups.md](docs/workstreams/ws-0315-gitea-followups.md) |
| `0299` | Live apply ntfy as the self-hosted push notification channel from latest origin/main | `merged` | [ws-0299-live-apply.md](docs/workstreams/ws-0299-live-apply.md) |
| `0300` | ADR 0300 live apply from latest origin/main | `merged` | [ws-0300-live-apply.md](docs/workstreams/ws-0300-live-apply.md) |
| `0304` | Live apply ADR 0304 from latest origin/main | `merged` | [ws-0304-live-apply.md](docs/workstreams/ws-0304-live-apply.md) |
| `0308` | Live apply ADR 0308 journey-aware entry routing and saved home selection from latest origin/main | `live_applied` | [ws-0308-journey-live-apply.md](docs/workstreams/ws-0308-journey-live-apply.md) |
| `0309` | Live apply task-oriented information architecture across the platform workbench from latest origin/main | `live_applied` | [ws-0309-live-apply.md](docs/workstreams/ws-0309-live-apply.md) |
| `0309` | Integrate ADR 0309 task-oriented information architecture onto main and replay it from exact mainline truth | `live_applied` | [ws-0309-main-integration.md](docs/workstreams/ws-0309-main-integration.md) |
| `0310` | Implement the first-run activation checklist and progressive capability reveal inside the interactive ops portal | `live_applied` | [ws-0310-live-apply.md](docs/workstreams/ws-0310-live-apply.md) |
| `0311` | Live apply a repo-managed cmdk command palette and universal open dialog on the Windmill operator access admin surface | `merged` | [ws-0311-live-apply.md](docs/workstreams/ws-0311-live-apply.md) |
| `0312` | Live apply the shared notification center and activity timeline across human surfaces | `live_applied` | [ws-0312-live-apply.md](docs/workstreams/ws-0312-live-apply.md) |
| `0312` | Integrate ADR 0312 exact-main verification and validation-gate hardening onto current origin/main | `merged` | [ws-0312-main-integration.md](docs/workstreams/ws-0312-main-integration.md) |
| `0313` | Live apply contextual help, glossary, and escalation drawer across the first-party portal surfaces | `live_applied` | [ws-0313-live-apply.md](docs/workstreams/ws-0313-live-apply.md) |
| `0315` | Live apply canonical page states and next-best-action guidance on the Windmill operator admin surface | `live_applied` | [ws-0315-live-apply.md](docs/workstreams/ws-0315-live-apply.md) |
| `0316` | Live apply journey analytics and onboarding success scorecards from latest origin/main | `merged` | [ws-0316-live-apply.md](docs/workstreams/ws-0316-live-apply.md) |
| `0317` | Live apply ADR 0317 Keycloak direct-API operator provisioning via SSH proxy | `live_applied` | [ws-0317-live-apply.md](docs/workstreams/ws-0317-live-apply.md) |
| `0319` | Live apply the first runtime-ai pool split with Nomad, Traefik, and Dapr on the latest mainline | `live_applied` | [ws-0319-live-apply.md](docs/workstreams/ws-0319-live-apply.md) |
| `0319` | Split the overloaded shared runtime into pool-scoped lanes with higher memory headroom and bounded autoscaling | `merged` | [adr-0319-runtime-pool-partitioning-and-memory-autoscaling-bundle.md](docs/workstreams/adr-0319-runtime-pool-partitioning-and-memory-autoscaling-bundle.md) |
| `0319` | Investigate recurring service restarts and uptime failures across the runtime pools | `merged` | [ws-0325-service-uptime-investigation.md](docs/workstreams/ws-0325-service-uptime-investigation.md) |
| `0319` | Refine the runtime-pool ADR bundle with battle-tested API-first OSS recommendations | `merged` | [ws-0329-runtime-library-fit.md](docs/workstreams/ws-0329-runtime-library-fit.md) |
| `0319` | Complete the phased runtime-pool transition after the first runtime-ai split | `merged` | [ws-0330-runtime-pool-transition-program.md](docs/workstreams/ws-0330-runtime-pool-transition-program.md) |
| `0319` | Fail closed before runtime-pool retirement or shared-runtime recovery can take down legacy services | `merged` | [ws-0333-service-uptime-recovery.md](docs/workstreams/ws-0333-service-uptime-recovery.md) |
| `0324` | Programmatic sharding roadmap for oversized service, ADR, discovery, and workstream surfaces | `merged` | [ws-0324-programmatic-doc-shards.md](docs/workstreams/ws-0324-programmatic-doc-shards.md) |
| `0330` | Prepare the repository for public GitHub publication as a generic and forkable reference platform | `merged` | [adr-0330-public-github-readiness-bundle.md](docs/workstreams/adr-0330-public-github-readiness-bundle.md) |
| `0340` | Dedicated Coolify Apps VM Separation — introduce coolify-apps-lv3 as the Coolify deployment server | `merged` | [0340-dedicated-coolify-apps-vm-separation.md](docs/adr/0340-dedicated-coolify-apps-vm-separation.md) |
<!-- END GENERATED: merged-workstreams -->

## Next For Forks

1. Replace example deployment values with your own inventory, publication, and identity choices.
2. Keep operator-local overlays and secret material outside committed public entrypoints.
3. Run validation before the first live apply in a fresh environment.
