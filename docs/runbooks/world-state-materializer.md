# World-State Materializer

## Purpose

ADR 0113 adds a repository-managed world-state subsystem that snapshots nine operational surfaces into Postgres and exposes them through a shared Python client.

## Repo Surfaces

- `migrations/0010_world_state_schema.sql`
- `platform/world_state/`
- `config/windmill/scripts/world-state/`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`

## What Gets Seeded

- `proxmox_vms`
- `service_health`
- `container_inventory`
- `netbox_topology`
- `dns_records`
- `tls_cert_expiry`
- `opentofu_drift`
- `openbao_secret_expiry`
- `maintenance_windows`

Each surface has a matching Windmill script plus a repo-managed schedule definition. The schedules are committed disabled so the first enablement still happens as an explicit live apply from `main`.

## Local Verification

Run the repository-side tests:

```bash
uv run --with pytest --with pyyaml pytest \
  tests/test_world_state_client.py \
  tests/test_world_state_workers.py \
  tests/test_world_state_repo_surfaces.py \
  tests/unit/test_world_state_materializer.py
```

Validate the wider repo before merge:

```bash
make validate
```

## Live Bring-Up

1. Apply the Windmill runtime role from `main` so the new scripts, disabled schedules, `WORLD_STATE_DSN`, and NATS worker credentials are seeded together.
2. Apply the Postgres migration on `postgres-lv3` against the same database named in `WORLD_STATE_DSN`.
3. Re-run the Windmill Postgres role or equivalent grants so `windmill_user` has `USAGE` on schema `world_state` plus table and sequence privileges there.
4. Enable the ADR 0113 schedules in Windmill.
5. Confirm rows appear in `world_state.current_view`.
6. Verify `platform.world_state.refreshed` events are published on NATS.

## Quick Checks

```bash
psql "$WORLD_STATE_DSN" -c "SELECT surface, collected_at, stale, is_expired FROM world_state.current_view ORDER BY surface;"
```

```bash
python -c "from platform.world_state.client import WorldStateClient; print(WorldStateClient().list_stale())"
```

## Operational Notes

- The Proxmox collector normalizes `null` CPU and memory readings to `0` for stopped VMs.
- The client can use `sqlite:///...` in tests and `postgres://...` in live environments.
- NATS publication is best-effort: the refresh still succeeds if `nats-py` is unavailable or the bus is temporarily unreachable.
- The current managed Windmill runtime defaults `WORLD_STATE_DSN` to the same Postgres database as Windmill itself unless an override is supplied.
- The first Postgres refresh must populate `world_state.current_view` with a plain `REFRESH MATERIALIZED VIEW` before later runs can switch to `CONCURRENTLY`; [platform/world_state/materializer.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/world_state/materializer.py) now handles that automatically.
- The Windmill worker checkout at `/srv/proxmox_florin_server` must contain the repo surfaces the collectors read (`config/`, `inventory/`, `scripts/`, `versions/`, and related runtime helpers), not just the seeded script files.
- `maintenance_windows` is not yet a clean Windmill-runtime surface because [scripts/maintenance_window_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/maintenance_window_tool.py) still assumes the controller-local bootstrap SSH key path when it builds the NATS tunnel.
