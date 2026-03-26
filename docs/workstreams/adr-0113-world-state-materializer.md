# Workstream ADR 0113: World-State Materializer

- ADR: [ADR 0113](../adr/0113-world-state-materializer.md)
- Title: Continuously refreshed canonical Postgres materialized view of platform state from Proxmox, NetBox, Docker, TLS, DNS, and OpenTofu — replaces ad hoc re-discovery in all agent workflows
- Status: merged
- Branch: `codex/ws-0113-live-apply`
- Worktree: `.worktrees/ws-0113-live-apply`
- Owner: codex
- Depends On: `adr-0054-netbox-topology`, `adr-0058-nats-event-bus`, `adr-0064-health-probe-contracts`, `adr-0080-maintenance-windows`, `adr-0085-opentofu-vm-lifecycle`, `adr-0091-drift-detection`, `adr-0098-postgres-ha`
- Conflicts With: `adr-0117-dependency-graph-runtime` (both read NetBox; coordinate on refresh interval)
- Shared Surfaces: `platform/world_state/`, `config/windmill/scripts/world-state/`, `roles/windmill_runtime/defaults/main.yml`, Postgres `world_state` schema

## Scope

- create Postgres migration `migrations/0010_world_state_schema.sql` — `world_state.snapshots` table, `world_state.surface_config` table, `world_state.current_view` materialised view
- create `platform/world_state/client.py` — `WorldStateClient` with `get()`, `get_at()`, and `list_stale()` methods
- create `config/windmill/scripts/world-state/refresh-proxmox-vms.py` — Proxmox API polling worker
- create `config/windmill/scripts/world-state/refresh-service-health.py` — health probe aggregator (calls ADR 0064 endpoints)
- create `config/windmill/scripts/world-state/refresh-container-inventory.py` — Docker inventory worker
- create `config/windmill/scripts/world-state/refresh-netbox-topology.py` — NetBox device/IP/VLAN import
- create `config/windmill/scripts/world-state/refresh-dns-records.py` — canonical DNS publication snapshot worker
- create `config/windmill/scripts/world-state/refresh-tls-certs.py` — step-ca API + TLS certificate scan
- create `config/windmill/scripts/world-state/refresh-opentofu-drift.py` — `tofu plan -json` runner and diff summariser
- create `config/windmill/scripts/world-state/refresh-openbao-leases.py` — OpenBao lease expiry reader
- create `config/windmill/scripts/world-state/refresh-maintenance-windows.py` — maintenance window store reader
- register all refresh workers as Windmill scheduled workflows with per-surface intervals from ADR 0113
- publish `platform.world_state.refreshed` NATS event after each successful snapshot insert

## Non-Goals

- Replacing NetBox as the system of record for topology — the materializer is a read-through cache
- Storing secret values — only lease metadata (TTL, path, expiry) is stored
- Building the dependency graph (ADR 0117) — that workstream will consume the materializer as its NetBox topology source

## Expected Repo Surfaces

- `migrations/0010_world_state_schema.sql`
- `platform/world_state/__init__.py`
- `platform/world_state/client.py`
- `platform/world_state/materializer.py`
- `platform/world_state/workers.py`
- `config/windmill/scripts/world-state/refresh-proxmox-vms.py`
- `config/windmill/scripts/world-state/refresh-service-health.py`
- `config/windmill/scripts/world-state/refresh-container-inventory.py`
- `config/windmill/scripts/world-state/refresh-netbox-topology.py`
- `config/windmill/scripts/world-state/refresh-dns-records.py`
- `config/windmill/scripts/world-state/refresh-tls-certs.py`
- `config/windmill/scripts/world-state/refresh-opentofu-drift.py`
- `config/windmill/scripts/world-state/refresh-openbao-leases.py`
- `config/windmill/scripts/world-state/refresh-maintenance-windows.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `docs/runbooks/world-state-materializer.md`
- `docs/adr/0113-world-state-materializer.md`
- `docs/workstreams/adr-0113-world-state-materializer.md`

## Expected Live Surfaces

- `world_state.current_view` in Postgres contains rows for all 9 implemented surfaces
- No surface has `is_expired = true` during normal operation
- `platform.world_state.refreshed` NATS messages are visible via `nats sub platform.world_state.refreshed`
- `WorldStateClient().get("proxmox_vms")` returns a non-empty list from the controller

## Verification

- Run `psql -c "SELECT surface, collected_at, stale FROM world_state.current_view;"` → all 9 surfaces present with recent timestamps after the first live sync
- Run `python -c "from platform.world_state.client import WorldStateClient; print(WorldStateClient().get('service_health'))"` → returns health dict
- Pause one refresh worker for 10 minutes and confirm `is_expired` flips to `true` for that surface
- Confirm `WorldStateClient().get("service_health")` raises `StaleDataError` when the surface is expired and `allow_stale=False`

## Live Apply Evidence

- 2026-03-26 live replay from latest `origin/main` plus this worktree synced the runtime checkout on `docker-runtime-lv3`, fixed the first-refresh materializer path, and granted `windmill_user` access to `world_state`.
- Verified live worker refreshes on `docker-runtime-lv3` for `proxmox_vms`, `container_inventory`, `netbox_topology`, `dns_records`, `tls_cert_expiry`, `opentofu_drift`, and `openbao_secret_expiry`.
- Verified Postgres live state on `postgres-lv3`: `world_state.current_view` is populated and queryable, with seven fresh rows and `pg_matviews.ispopulated = true`.
- Focused repository validation passed with `uv run --with pytest --with pyyaml pytest tests/test_world_state_workers.py tests/test_world_state_repo_surfaces.py tests/unit/test_world_state_materializer.py -q` and `python3 -m compileall config/windmill/scripts/world-state platform/world_state`.

## Remaining Merge-To-Main Follow-Up

- Merge the `windmill_postgres` world-state grant tasks so future replays do not require the manual `GRANT ... ON SCHEMA world_state` recovery.
- Merge the wrapper import-order fix and the first-refresh fallback so future Windmill worker syncs can run without manual file sync on `docker-runtime-lv3`.
- Reconcile the shared Windmill runtime template with the concurrent test-runner workstream so `WORLD_STATE_DSN`, NATS, ledger, Proxmox, and test-runner variables coexist in one managed `runtime.env.ctmpl`.
- Finish live verification for `service_health` and `maintenance_windows`; the former was still long-running during this replay, and the latter still depends on a controller-coupled SSH tunnel path in `scripts/maintenance_window_tool.py`.

## Merge Criteria

- All 9 refresh workers are seeded and scheduled in Windmill from repo-managed defaults
- `WorldStateClient` can be imported and used in a Windmill workflow script
- Stale detection is covered by automated SQLite-backed tests and ready for live verification
- NATS refresh publication is implemented as best-effort and ready for live verification once the worker runtime has NATS credentials

## Notes For The Next Assistant

- The Proxmox API worker must handle the case where a VM is powered off: Proxmox returns CPU/memory as null for stopped VMs; treat null utilisation as 0 rather than raising an exception
- The `REFRESH MATERIALIZED VIEW CONCURRENTLY` command requires the view to have a unique index; ensure `world_state.current_view` has `CREATE UNIQUE INDEX` on `(surface)` before the first concurrent refresh
- The OpenTofu drift refresh worker runs `tofu plan -json` which can take 30–60 seconds; its Windmill workflow timeout must be at least 120 seconds
- Surface config rows in `world_state.surface_config` should be inserted by the migration and not modified at runtime; they are the definition of what "stale" means for each surface
