# Workstream ws-0303-live-apply: Live Apply ADR 0303 From Latest `origin/main`

- ADR: [ADR 0303](../adr/0303-pgaudit-for-postgresql-query-and-privilege-change-audit-logging.md)
- Title: Enable PostgreSQL pgaudit, ship structured audit signals to Loki and Prometheus, and route unknown-role alerts to ntfy plus NATS
- Status: in_progress
- Included In Repo Version: N/A
- Branch-Local Receipt: pending
- Canonical Mainline Receipt: pending
- Live Applied In Platform Version: N/A
- Implemented On: pending
- Live Applied On: pending
- Branch: `codex/ws-0303-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0303-main-integration`
- Owner: codex
- Depends On: `adr-0026-dedicated-postgresql-vm-for-shared-state`, `adr-0052-loki-as-central-log-aggregation`, `adr-0080-maintenance-window-and-change-suppression-protocol`, `adr-0097-alerting-routing-and-oncall-runbook-model`, `adr-0276-nats-jetstream-as-the-platform-event-bus`, `adr-0299-ntfy-as-the-self-hosted-push-notification-channel-for-programmatic-alert-delivery`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0303`, `docs/workstreams/ws-0303-live-apply.md`, `docs/runbooks/postgres-audit.md`, `inventory/host_vars/proxmox_florin.yml`, `playbooks/services/guest-log-shipping.yml`, `roles/postgres_vm/`, `roles/loki_log_agent/`, `roles/monitoring_vm/`, `roles/alertmanager_runtime/`, `config/pgaudit/`, `config/alertmanager/`, `config/event-taxonomy.yaml`, `receipts/live-applies/`, `tests/`, `workstreams.yaml`

## Scope

- enable `pgaudit` on the live `postgres-lv3` primary managed by the current `postgres_vm` role path
- create repo-managed sensitive-table and approved-role catalogs for object audit and unknown connection detection
- parse PostgreSQL audit and connection logs in Alloy, expose counters to Prometheus, and alert on privilege bursts plus unexpected login roles
- bridge the unexpected-role alert path into the existing ntfy routing and a durable NATS event publication
- record end-to-end live-apply evidence and leave the workstream in a merge-safe state

## Non-Goals

- migrating the live PostgreSQL runtime to the deferred `postgres_ha` path
- changing protected release surfaces on this workstream branch before the exact-main integration step
- introducing long-term archival outside the existing Loki retention boundary

## Expected Repo Surfaces

- `docs/adr/0303-pgaudit-for-postgresql-query-and-privilege-change-audit-logging.md`
- `docs/runbooks/postgres-audit.md`
- `docs/runbooks/postgres-down.md`
- `docs/workstreams/ws-0303-live-apply.md`
- `workstreams.yaml`
- `inventory/host_vars/proxmox_florin.yml`
- `playbooks/services/guest-log-shipping.yml`
- `roles/postgres_vm/`
- `roles/loki_log_agent/`
- `roles/monitoring_vm/`
- `roles/alertmanager_runtime/`
- `collections/ansible_collections/lv3/platform/roles/postgres_vm/`
- `collections/ansible_collections/lv3/platform/roles/loki_log_agent/`
- `collections/ansible_collections/lv3/platform/roles/monitoring_vm/`
- `collections/ansible_collections/lv3/platform/roles/alertmanager_runtime/`
- `config/pgaudit/`
- `config/alertmanager/alertmanager.yml`
- `config/alertmanager/rules/platform.yml`
- `config/controller-local-secrets.json`
- `config/event-taxonomy.yaml`
- `receipts/live-applies/`
- `tests/`

## Expected Live Surfaces

- `postgres-lv3` with `shared_preload_libraries = 'pgaudit'`, object audit grants, and `pgaudit` extensions on the writable databases
- PostgreSQL audit and connection logs in Loki with structured labels for `db`, `db_role`, and `command_class`
- Prometheus scrape visibility into the Alloy metrics endpoint on `postgres-lv3`
- critical notification and NATS publication for unknown PostgreSQL login roles

## Ownership Notes

- this workstream owns the live PostgreSQL audit rollout, the monitoring-side alert relay, and the branch-local evidence bundle
- `postgres-lv3` and `monitoring-lv3` are shared live surfaces, so the exact-main replay must refresh from `origin/main` immediately before final integration
- protected integration files remain deferred until the final exact-main integration step

## Progress Notes

- Discovery confirmed the live writable PostgreSQL node still follows the `postgres_vm` path, not the deferred `postgres_ha` role.
- The initial implementation will therefore land on the real production path and update ADR 0303 where the accepted design overstated `pgaudit` support for connection events and per-role object audit.
