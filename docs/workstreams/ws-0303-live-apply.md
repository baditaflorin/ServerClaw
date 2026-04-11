# Workstream ws-0303-live-apply: Live Apply ADR 0303 From Latest `origin/main`

- ADR: [ADR 0303](../adr/0303-pgaudit-for-postgresql-query-and-privilege-change-audit-logging.md)
- Title: Enable PostgreSQL pgaudit, ship structured audit signals to Loki and Prometheus, and route unknown-role alerts to ntfy plus NATS
- Status: live_applied
- Included In Repo Version: 0.177.122
- Branch-Local Receipt: `receipts/live-applies/2026-03-31-adr-0303-pgaudit-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-31-adr-0303-pgaudit-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.77
- Implemented On: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0303-main-final`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0303-main-integration/.worktrees/ws-0303-main-final`
- Owner: codex
- Depends On: `adr-0026-dedicated-postgresql-vm-for-shared-state`, `adr-0052-loki-as-central-log-aggregation`, `adr-0080-maintenance-window-and-change-suppression-protocol`, `adr-0097-alerting-routing-and-oncall-runbook-model`, `adr-0276-nats-jetstream-as-the-platform-event-bus`, `adr-0299-ntfy-as-the-self-hosted-push-notification-channel-for-programmatic-alert-delivery`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0303-live-apply.md`, `docs/adr/0303`, `docs/adr/.index.yaml`, `docs/runbooks/postgres-audit.md`, `docs/runbooks/postgres-down.md`, `docs/runbooks/playbook-execution-model.md`, `docs/runbooks/vulnerability-budget-gates.md`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`, `inventory/host_vars/proxmox-host.yml`, `playbooks/postgres-vm.yml`, `playbooks/monitoring-stack.yml`, `playbooks/nats-jetstream.yml`, `playbooks/services/guest-log-shipping.yml`, `collections/ansible_collections/lv3/platform/roles/postgres_vm/**`, `collections/ansible_collections/lv3/platform/roles/loki_log_agent/**`, `collections/ansible_collections/lv3/platform/roles/monitoring_vm/**`, `collections/ansible_collections/lv3/platform/roles/alertmanager_runtime/**`, `collections/ansible_collections/lv3/platform/roles/linux_guest_firewall/**`, `config/pgaudit/**`, `config/alertmanager/alertmanager.yml`, `config/alertmanager/rules/platform.yml`, `config/controller-local-secrets.json`, `config/event-taxonomy.yaml`, `platform/events/publisher.py`, `platform/retry/classification.py`, `scripts/drift_lib.py`, `scripts/published_artifact_secret_scan.py`, `scripts/service_id_resolver.py`, `receipts/live-applies/2026-03-31-adr-0303-*.json`, `receipts/live-applies/evidence/2026-03-31-adr-0303-*`, `receipts/live-applies/evidence/2026-03-31-ws-0303-*`, `receipts/ops-portal-snapshot.html`, `receipts/sbom/**`, `tests/`

## Scope

- enable `pgaudit` on the live `postgres` primary managed by the current `postgres_vm` role path
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
- `inventory/host_vars/proxmox-host.yml`
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

- `postgres` with `shared_preload_libraries = 'pgaudit'`, object audit grants, and `pgaudit` extensions on the writable databases
- PostgreSQL audit and connection logs in Loki with structured labels for `db`, `db_role`, and `command_class`
- Prometheus scrape visibility into the Alloy metrics endpoint on `postgres`
- critical notification and NATS publication for unknown PostgreSQL login roles

## Ownership Notes

- this workstream owns the live PostgreSQL audit rollout, the monitoring-side alert relay, and the branch-local evidence bundle
- `postgres` and `monitoring` are shared live surfaces, so the exact-main replay must refresh from `origin/main` immediately before final integration
- protected integration files remain deferred until the final exact-main integration step

## Progress Notes

- Discovery confirmed the live writable PostgreSQL node still follows the `postgres_vm` path, not the deferred `postgres_ha` role.
- The initial implementation will therefore land on the real production path and update ADR 0303 where the accepted design overstated `pgaudit` support for connection events and per-role object audit.

## Verification

- `uv run --with pyyaml python3 scripts/release_manager.py --bump patch ...`
  cut release `0.177.122` and refreshed the canonical truth surfaces, captured in `receipts/live-applies/evidence/2026-03-31-ws-0303-mainline-final-release-write-r2-0.177.122.txt`.
- `uv run --with pytest --with pyyaml python3 -m pytest -q tests/test_guest_log_shipping_playbook.py tests/test_monitoring_vm_role.py tests/unit/test_event_taxonomy.py tests/test_service_id_resolver.py`
  passed with `29 passed in 0.75s`, captured in `receipts/live-applies/evidence/2026-03-31-ws-0303-mainline-final-targeted-pytest-r4-0.177.122.txt`.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=guest-log-shipping env=production`
  passed on the released candidate and re-verified the guarded wrapper path, Prometheus scrape assertions, and the post-apply Restic trigger. The final recap reported `docker-runtime : ok=17 changed=2 unreachable=0 failed=0`, and the backup trigger recorded `receipts/restic-backups/20260331T192735Z.json` with config snapshot `1ad975dcc1b3be1be5b48d2ea3f7ae8b730571e840317f53498bb7467b099f78` plus `versions/stack.yaml` snapshot `68960faae1f91e15d644b7d93adcd279953de9acb561f9e494968c37a726bc3c`, preserved in `receipts/live-applies/evidence/2026-03-31-ws-0303-mainline-final-live-apply-service-guest-log-shipping-r5-0.177.122.txt`.
- `make check-build-server`
  passed from committed source `99b51ba1572be6df3411d4b4ef499e660a1dd7e0` and re-verified the immutable snapshot upload path on `docker-build`, captured in `receipts/live-applies/evidence/2026-03-31-ws-0303-mainline-final-check-build-server-r2-0.177.122.txt`.
- `make remote-validate`
  passed on the released candidate, with the remote lane selecting `repository-structure-and-schema`, `generated-artifact-and-canonical-truth`, `service-syntax-and-unit`, and `remote-builder`, captured in `receipts/live-applies/evidence/2026-03-31-ws-0303-mainline-final-remote-validate-r2-0.177.122.txt`.
- `make pre-push-gate`
  passed on the released candidate. The remote runner truthfully reported transient `502 Bad Gateway` pulls for `registry.example.com/check-runner/infra:2026.03.23`, then `run_gate_fallback` reran only `packer-validate` and `tofu-validate` locally and merged the passing result back into `.local/validation-gate/last-run.json`, captured in `receipts/live-applies/evidence/2026-03-31-ws-0303-mainline-final-pre-push-gate-r3-0.177.122.txt`.
- The earlier final unknown-role smoke remains the end-to-end proof for the alert path: Alertmanager exposed `PostgresUnknownRoleConnection` for role `adr0303_smoke_9279c7f7`, the monitoring relay logged a successful `POST /alerts/pgaudit-unknown-role`, and JetStream advanced to seq `10972` on `platform.security.pgaudit_unknown_role`, preserved in `receipts/live-applies/evidence/2026-03-31-ws-0303-mainline-final-pgaudit-unknown-role-smoke-r11-0.177.120.txt`.

## Results

- ADR 0303 is now implemented in repository version `0.177.122` and first verified live on platform version `0.130.77`.
- The exact-main release closeout preserved the already-current platform baseline `0.130.78` while proving the released `0.177.122` candidate end to end through the guarded `live-apply-service`, remote validation, and full pre-push gate paths.
- The branch-local receipt records the first live rollout and smoke evidence gathered before the release cut; the canonical mainline receipt records the released `main` integration on top of latest `origin/main`.
- During the earlier final smoke closeout, the repo-managed `guest-network-policy` replay corrected a missing live `monitoring -> docker-runtime:4222` firewall allow that was preventing the relay from reaching NATS. The broad play still surfaced an unrelated existing `postgres-replica` SSH reachability failure, which remains outside ADR 0303 scope and is preserved as evidence instead of being hidden.
