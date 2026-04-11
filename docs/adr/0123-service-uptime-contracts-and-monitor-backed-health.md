# ADR 0123: Service Uptime Contracts And Monitor-Backed Health

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.121.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

The repository already contains the main pieces of a service uptime model:

- ADR 0064 defines liveness and readiness contracts in `config/health-probe-catalog.json`
- ADR 0075 binds service identities and operator-facing metadata in `config/service-capability-catalog.json`
- ADR 0027 seeds Uptime Kuma from `config/uptime-kuma/monitors.json`
- ADR 0092 and ADR 0093 expose internal status through the platform API and the interactive ops portal

Those paths were still only loosely connected. `config/uptime-kuma/monitors.json` remained a hand-maintained duplicate of the health-probe catalog, while the internal health surfaces were not using the health-probe contract for most services. The result was that `https://uptime.example.com/dashboard/3` could contain useful live data, but the service catalog, world-state, API gateway, and portal could drift from it or only show a smaller subset of services.

## Decision

We will make the **health-probe catalog the canonical uptime contract** and drive both Uptime Kuma configuration and internal service-health views from it.

### Contract model

The uptime contract now spans three layers:

1. `config/health-probe-catalog.json`
   - canonical liveness and readiness probes
   - canonical `uptime_kuma.enabled` and `uptime_kuma.monitor` definitions
2. `config/uptime-kuma/monitors.json`
   - generated artifact for Uptime Kuma reconciliation
3. `config/service-capability-catalog.json`
   - stable service identity plus `uptime_monitor_name` binding for operator-facing surfaces

### Internal health model

`platform/world_state/workers.py` will probe services from the health-probe contract instead of guessing from `public_url` or `internal_url` alone.

The collector will:

- prefer `readiness` probes when they are directly executable from the controller or worker
- fall back to `liveness` probes when readiness is not directly executable
- fall back to the service catalog URL only when the contract probe cannot be executed from the worker

### API and portal model

The platform API gateway will expose platform health from the service catalog plus world-state health snapshots, not only from the smaller set of proxied API services.

This means:

- `GET /v1/platform/health` returns active services from the service catalog with live contract-backed status
- `GET /v1/platform/health/{service_id}` returns one service record for targeted checks
- the interactive ops portal can show real service status for most managed services instead of only the proxied gateway subset

## Consequences

### Positive

- one canonical contract now drives Uptime Kuma monitor generation and internal health reporting
- most services gain real health visibility inside the platform API and interactive ops portal
- repo validation can detect drift between `health-probe-catalog.json` and `config/uptime-kuma/monitors.json`
- adding or changing a service health surface becomes a contract update instead of a manual multi-file sync

### Negative / Trade-offs

- the world-state collector still cannot execute every contract kind from every environment; `command` and `systemd` probes may need fallback handling
- `config/uptime-kuma/monitors.json` remains committed for deployment workflows, even though it is generated
- operators must regenerate the monitor artifact when changing health-probe contracts

## Boundaries

- This ADR does not replace full integration tests or SLO tracking.
- This ADR does not require a live platform apply to become repository truth.
- This ADR does not make Uptime Kuma the sole health authority; role verify tasks and world-state retain their own execution paths.

## Related ADRs

- ADR 0027: Uptime Kuma on the Docker runtime VM
- ADR 0064: Health probe contracts for all services
- ADR 0075: Service capability catalog
- ADR 0092: Unified platform API gateway
- ADR 0093: Interactive ops portal
- ADR 0113: World-state materializer
