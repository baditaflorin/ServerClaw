# Workstream ws-0292-live-apply: Live Apply ADR 0292 From Latest `origin/main`

- ADR: [ADR 0292](../adr/0292-lago-as-the-usage-metering-and-billing-api-layer.md)
- Title: Deploy Lago as the repo-managed usage metering and billing API layer, publish `billing.lv3.org`, and verify metered ingestion end to end
- Status: in_progress
- Branch: `codex/ws-0292-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0292-live-apply-r2`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0042-postgresql-as-the-shared-relational-database`, `adr-0063-keycloak-sso-for-internal-services`, `adr-0077-compose-secret-injection-pattern`, `adr-0086-backup-and-recovery`, `adr-0276-nats-jetstream-as-the-platform-event-bus`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `Makefile`, `docs/adr/0292`, `docs/workstreams/ws-0292-live-apply.md`, `docs/runbooks/configure-lago.md`, `docs/site-generated/architecture/dependency-graph.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `playbooks/lago.yml`, `playbooks/services/lago.yml`, `collections/ansible_collections/lv3/platform/playbooks/lago.yml`, `collections/ansible_collections/lv3/platform/playbooks/services/lago.yml`, `roles/lago_postgres/`, `roles/lago_runtime/`, `roles/api_gateway_runtime/`, `roles/nginx_edge_publication/`, `scripts/api_gateway/main.py`, `scripts/generate_platform_vars.py`, `config/*catalog*.json`, `config/ansible-execution-scopes.yaml`, `config/ansible-role-idempotency.yml`, `config/prometheus/file_sd/https_tls_targets.yml`, `config/prometheus/rules/https_tls_alerts.yml`, `config/uptime-kuma/monitors.json`, `receipts/image-scans/`, `receipts/live-applies/`, `receipts/ops-portal-snapshot.html`, `tests/`

## Scope

- deploy a repo-managed Lago runtime on `docker-runtime-lv3` using shared PostgreSQL and a service-local Redis/PDF companion stack
- publish `billing.lv3.org` through the shared NGINX edge with the browser and management paths protected by the shared edge OIDC flow
- expose a public ingest path at `billing.lv3.org/api/v1/events` through a narrow API-gateway adapter that enforces per-producer ingest tokens and publishes rejected payloads to NATS JetStream
- seed the initial Lago catalog, customer, subscription, and smoke verification contract from repo-managed Ansible defaults
- record branch-local live-apply evidence and exactly document any merge-to-`main` follow-up that must wait for protected integration surfaces

## Non-Goals

- introducing Lago payment collection or external payment-processor integrations
- claiming OSS Lago natively supports premium scoped API-key permissions that are not available on the self-hosted open-source path
- updating protected release surfaces on this workstream branch before the exact-main integration step

## Expected Repo Surfaces

- `workstreams.yaml`
- `Makefile`
- `docs/workstreams/ws-0292-live-apply.md`
- `docs/adr/0292-lago-as-the-usage-metering-and-billing-api-layer.md`
- `docs/runbooks/configure-lago.md`
- `docs/site-generated/architecture/dependency-graph.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `playbooks/lago.yml`
- `playbooks/services/lago.yml`
- `collections/ansible_collections/lv3/platform/playbooks/lago.yml`
- `collections/ansible_collections/lv3/platform/playbooks/services/lago.yml`
- `collections/ansible_collections/lv3/platform/roles/lago_postgres/`
- `collections/ansible_collections/lv3/platform/roles/lago_runtime/`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/`
- `scripts/api_gateway/main.py`
- `scripts/generate_platform_vars.py`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `config/api-gateway-catalog.json`
- `config/certificate-catalog.json`
- `config/command-catalog.json`
- `config/controller-local-secrets.json`
- `config/data-catalog.json`
- `config/dependency-graph.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `config/secret-catalog.json`
- `config/service-capability-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/subdomain-catalog.json`
- `config/subdomain-exposure-registry.json`
- `config/uptime-kuma/monitors.json`
- `config/workflow-catalog.json`
- `receipts/image-scans/`
- `receipts/live-applies/`
- `receipts/ops-portal-snapshot.html`
- `tests/`

## Expected Live Surfaces

- a running Lago stack on `docker-runtime-lv3`
- public hostname `billing.lv3.org`
- protected browser and management API access on `billing.lv3.org`
- public event ingest at `billing.lv3.org/api/v1/events`
- NATS publication for rejected billing-event payloads
- a seeded smoke customer/subscription whose usage can be observed through Lago after synthetic ingestion

## Ownership Notes

- this workstream owns the first repo-managed Lago deployment, the billing-edge publication shape, the ingress adapter contract, and the branch-local live-apply evidence
- `docker-runtime-lv3`, `nginx-lv3`, and the existing API gateway are shared live surfaces, so changes must stay narrow, replayable, and non-destructive
- release files, top-level integrated status summaries, and canonical platform-version truth remain deferred until the merge-to-`main` exact replay step

## Plan Snapshot

- add the missing workstream state first so concurrent agents can see branch ownership
- implement Lago runtime, seeding, and billing edge publication in the repo’s standard service pattern
- extend the API gateway with the smallest possible ingest adapter that enforces producer tokens and emits rejected events to NATS
- run targeted tests, full validation gates, and a governed live apply
- capture receipts, update ADR metadata and the runbook, and leave exact merge-to-`main` follow-up explicitly documented
