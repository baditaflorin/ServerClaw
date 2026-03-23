# ADR 0113: World-State Materializer

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.112.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

Every agent workflow, incident triage run, and dry-run diff operation needs to know the current state of the platform: which VMs are running, which services are healthy, what version is deployed, what TLS certificates are near expiry, which DNS names resolve to which addresses. Today that information is gathered on demand by calling each source system individually.

This ad hoc re-discovery pattern has several costs:

- **Latency**: a workflow that needs Proxmox VM state, NetBox topology data, and current TLS certificate expiry must make three separate API calls before it can begin reasoning. This is slow and brittle.
- **Inconsistency**: two simultaneous workflows can observe different snapshots of reality if one queries NetBox before a change propagates and the other queries after.
- **Tool proliferation**: every new workflow that needs "what hosts exist" must either hard-code the NetBox API call or depend on a shared helper that is not consistently used.
- **Re-discovery noise in audit logs**: re-discovery API calls fill the mutation ledger (ADR 0115) and workflow logs with read-only chatter that obscures actual mutations.
- **No historical view**: ad hoc queries return current state only; there is no way to reconstruct what the platform state looked like at a specific point in time.

The continuous drift detection system (ADR 0091) already snapshots some state for comparison purposes. The world-state materializer generalises that idea into a platform-wide canonical state store.

## Decision

We will build a **world-state materializer** that continuously refreshes a canonical materialized view of platform state into a dedicated Postgres schema (`world_state`) on the platform Postgres instance (VM 150).

### Collected surfaces

| Surface | Source | Refresh interval | Stale threshold |
|---|---|---|---|
| VM inventory and runtime state | Proxmox API or observed-state fallback | 60 s | 5 min |
| Service health | Health probe contracts (ADR 0064) and service capability catalog | 30 s | 2 min |
| Container inventory | Docker API (per host) | 60 s | 5 min |
| Network topology | NetBox API or inventory fallback | 5 min | 30 min |
| DNS records | Subdomain catalog and resolver-facing publication data | 5 min | 30 min |
| TLS certificate expiry | step-ca scan and external TLS scan | 1 hr | 6 hr |
| OpenTofu drift summary | OpenTofu drift command output | 15 min | 1 hr |
| OpenBao secret expiry | OpenBao lease API or secret-catalog fallback | 5 min | 30 min |
| Maintenance windows | Maintenance window store (ADR 0080) | 1 min | 5 min |

### Schema (abbreviated)

```sql
-- world_state.snapshots: one row per surface per refresh cycle
CREATE TABLE world_state.snapshots (
    id          BIGSERIAL PRIMARY KEY,
    surface     TEXT NOT NULL,              -- 'proxmox_vms', 'service_health', etc.
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    data        JSONB NOT NULL,
    stale       BOOLEAN NOT NULL DEFAULT FALSE
);

-- world_state.current_view: materialised summary, refreshed on each snapshot insert
CREATE MATERIALIZED VIEW world_state.current_view AS
SELECT
    s.surface,
    s.data,
    s.collected_at,
    s.stale,
    (now() - s.collected_at) > make_interval(secs => t.stale_threshold_secs) AS is_expired
FROM world_state.snapshots s
JOIN world_state.surface_config t ON t.surface = s.surface
WHERE s.id IN (
    SELECT MAX(id) FROM world_state.snapshots GROUP BY surface
);
```

### Refresh workers

Each surface has a Windmill workflow that runs on the corresponding refresh interval:

```
config/windmill/scripts/world-state/
├── refresh-proxmox-vms.py
├── refresh-service-health.py
├── refresh-container-inventory.py
├── refresh-netbox-topology.py
├── refresh-dns-records.py
├── refresh-tls-certs.py
├── refresh-opentofu-drift.py
├── refresh-openbao-leases.py
└── refresh-maintenance-windows.py
```

Each worker follows a consistent pattern:

1. Fetch data from the source system via its API.
2. Validate the response against the surface JSON schema.
3. Insert a new row into `world_state.snapshots`.
4. Trigger a `REFRESH MATERIALIZED VIEW CONCURRENTLY` on `world_state.current_view`.
5. Emit a `world_state.refreshed` event to NATS (ADR 0058).

### Staleness handling

Stale detection is explicit. When `is_expired` is true for a surface, the world-state API returns the stale data with a `stale: true` flag and the `collected_at` timestamp. Consumers (goal compiler, triage engine, diff engine) must decide whether stale data is acceptable for their operation. The goal compiler (ADR 0112) rejects HIGH and CRITICAL risk compilations when any required surface is stale.

### Query API

Consumers query world state through a thin Python module `platform/world_state/client.py`:

```python
from platform.world_state.client import WorldStateClient

ws = WorldStateClient()

# Current VM inventory
vms = ws.get("proxmox_vms")               # returns list of VM dicts, raises if stale

# Current service health
health = ws.get("service_health", allow_stale=True)   # returns stale data if fresh unavailable

# Point-in-time query (for replay/incident analysis)
past_vms = ws.get_at("proxmox_vms", at="2026-03-24T02:00:00Z")
```

The client is available to Windmill workflows, the platform CLI, and the agent observation loop without any additional service dependency.

## Implementation Notes

- Repository implementation landed in `0.112.0` with the shared [platform/world_state/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/world_state) package, the Postgres schema migration at [migrations/0010_world_state_schema.sql](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/migrations/0010_world_state_schema.sql), the seeded Windmill workers under [config/windmill/scripts/world-state/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/world-state), and schedule registration through [collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml).
- The repository now seeds all ADR 0113 workers and schedules, but live Windmill enablement and the first Postgres migration/apply remain platform-version work and therefore do not bump `platform_version` yet.

## Consequences

**Positive**

- Workflows query a single local Postgres view instead of calling four different APIs; this removes most agent tool-chatter and reduces workflow latency.
- The point-in-time query enables incident replay: the triage engine (ADR 0114) can reconstruct what the world looked like when an incident fired.
- Drift detection (ADR 0091) can consume world state directly instead of maintaining its own collection logic.
- The dependency graph (ADR 0117) can be derived from NetBox topology snapshots rather than querying NetBox live on every traversal.

**Negative / Trade-offs**

- Every surface needs a refresh worker and a stale threshold; getting these wrong introduces subtle bugs (stale data treated as fresh, or overly aggressive re-querying).
- The Postgres instance becomes a critical dependency for all agent reasoning; existing Postgres HA (ADR 0098) mitigates this but does not eliminate it.
- The materialised view must be refreshed atomically; concurrent refreshes from multiple workers must be serialised per surface to avoid snapshot interleaving.

## Boundaries

- The world-state materializer collects and stores state. It does not make decisions. Decision logic belongs in the goal compiler (ADR 0112), triage engine (ADR 0114), and diff engine (ADR 0120).
- It does not replace NetBox as the source of truth for topology. NetBox is still the system of record; the materializer is a read-through cache.
- It does not store secrets. Secret expiry metadata (not the secret values) is collected via the OpenBao lease API.

## Related ADRs

- ADR 0054: NetBox topology (primary source for network and host topology snapshots)
- ADR 0058: NATS event bus (refresh events published here)
- ADR 0064: Health probe contracts (service health surface)
- ADR 0080: Maintenance windows (maintenance window surface)
- ADR 0085: OpenTofu VM lifecycle (OpenTofu drift surface)
- ADR 0091: Continuous drift detection (consumes world state instead of re-collecting)
- ADR 0098: Postgres HA (underlying storage for the world_state schema)
- ADR 0112: Deterministic goal compiler (queries world state for scope binding)
- ADR 0114: Rule-based incident triage engine (queries world state for triage context)
- ADR 0117: Service dependency graph (derived from NetBox topology snapshots)
- ADR 0120: Dry-run semantic diff engine (queries world state for desired vs observed delta)
