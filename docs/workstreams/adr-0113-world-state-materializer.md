# Workstream ADR 0113: World-State Materializer

- ADR: [ADR 0113](../adr/0113-world-state-materializer.md)
- Title: Continuously refreshed canonical Postgres materialized view of platform state from Proxmox, NetBox, Docker, TLS, DNS, and OpenTofu — replaces ad hoc re-discovery in all agent workflows
- Status: ready
- Branch: `codex/adr-0113-world-state-materializer`
- Worktree: `../proxmox_florin_server-world-state`
- Owner: codex
- Depends On: `adr-0054-netbox-topology`, `adr-0058-nats-event-bus`, `adr-0064-health-probe-contracts`, `adr-0080-maintenance-windows`, `adr-0085-opentofu-vm-lifecycle`, `adr-0091-drift-detection`, `adr-0098-postgres-ha`
- Conflicts With: `adr-0117-dependency-graph-runtime` (both read NetBox; coordinate on refresh interval)
- Shared Surfaces: `platform/world_state/`, `windmill/world-state/`, Postgres `world_state` schema

## Scope

- create Postgres migration `migrations/0010_world_state_schema.sql` — `world_state.snapshots` table, `world_state.surface_config` table, `world_state.current_view` materialised view
- create `platform/world_state/client.py` — `WorldStateClient` with `get()`, `get_at()`, and `list_stale()` methods
- create `windmill/world-state/refresh-proxmox-vms.py` — Proxmox API polling worker
- create `windmill/world-state/refresh-service-health.py` — health probe aggregator (calls ADR 0064 endpoints)
- create `windmill/world-state/refresh-netbox-topology.py` — NetBox device/IP/VLAN import
- create `windmill/world-state/refresh-tls-certs.py` — step-ca API + TLS certificate scan
- create `windmill/world-state/refresh-opentofu-drift.py` — `tofu plan -json` runner and diff summariser
- create `windmill/world-state/refresh-openbao-leases.py` — OpenBao lease expiry reader
- create `windmill/world-state/refresh-maintenance-windows.py` — maintenance window store reader
- register all refresh workers as Windmill scheduled workflows with per-surface intervals from ADR 0113
- publish `world_state.refreshed` NATS event after each successful snapshot insert

## Non-Goals

- Replacing NetBox as the system of record for topology — the materializer is a read-through cache
- Storing secret values — only lease metadata (TTL, path, expiry) is stored
- Building the dependency graph (ADR 0117) — that workstream will consume the materializer as its NetBox topology source

## Expected Repo Surfaces

- `migrations/0010_world_state_schema.sql`
- `platform/world_state/__init__.py`
- `platform/world_state/client.py`
- `windmill/world-state/refresh-proxmox-vms.py`
- `windmill/world-state/refresh-service-health.py`
- `windmill/world-state/refresh-netbox-topology.py`
- `windmill/world-state/refresh-tls-certs.py`
- `windmill/world-state/refresh-opentofu-drift.py`
- `windmill/world-state/refresh-openbao-leases.py`
- `windmill/world-state/refresh-maintenance-windows.py`
- `docs/adr/0113-world-state-materializer.md`
- `docs/workstreams/adr-0113-world-state-materializer.md`

## Expected Live Surfaces

- `world_state.current_view` in Postgres contains rows for all 9 surfaces
- No surface has `is_expired = true` during normal operation
- `world_state.refreshed` NATS messages are visible via `nats sub world_state.refreshed`
- `WorldStateClient().get("proxmox_vms")` returns a non-empty list from the controller

## Verification

- Run `psql -c "SELECT surface, collected_at, stale FROM world_state.current_view;"` → all 9 surfaces present with recent timestamps
- Run `python -c "from platform.world_state.client import WorldStateClient; print(WorldStateClient().get('service_health'))"` → returns health dict
- Pause one refresh worker for 10 minutes and confirm `is_expired` flips to `true` for that surface
- Confirm `WorldStateClient().get("service_health")` raises `StaleDataError` when the surface is expired and `allow_stale=False`

## Merge Criteria

- All 9 refresh workers scheduled and producing rows in `world_state.snapshots`
- `WorldStateClient` can be imported and used in a Windmill workflow script
- Stale detection tested manually
- NATS refresh events verified

## Notes For The Next Assistant

- The Proxmox API worker must handle the case where a VM is powered off: Proxmox returns CPU/memory as null for stopped VMs; treat null utilisation as 0 rather than raising an exception
- The `REFRESH MATERIALIZED VIEW CONCURRENTLY` command requires the view to have a unique index; ensure `world_state.current_view` has `CREATE UNIQUE INDEX` on `(surface)` before the first concurrent refresh
- The OpenTofu drift refresh worker runs `tofu plan -json` which can take 30–60 seconds; its Windmill workflow timeout must be at least 120 seconds
- Surface config rows in `world_state.surface_config` should be inserted by the migration and not modified at runtime; they are the definition of what "stale" means for each surface
