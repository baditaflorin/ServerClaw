# ADR 0376: Identity Core VM Isolation and Aggressive Health Watchdog

- Status: Accepted
- Implementation Status: Not Implemented
- Date: 2026-04-06
- Tags: vm-topology, identity, keycloak, step-ca, openbao, api-gateway, watchdog, health, reliability

## Context

`runtime-control-lv3` (VMID 192, `10.10.10.92`) currently hosts twelve services:

| Service | Role | Critical? |
|---|---|---|
| Keycloak | Identity / SSO | **Yes** — 22 OIDC clients depend on it |
| Step-CA | Certificate authority | **Yes** — all TLS cert issuance depends on it |
| OpenBao | Secrets vault | **Yes** — all service secret injection depends on it |
| API Gateway | Platform entry point | **Yes** — unified API surface for agents and operators |
| Gitea | Git forge | No |
| Harbor | Container registry | No |
| Mail Platform | SMTP relay | No |
| OpenFGA | Authorization engine | No |
| Temporal | Workflow engine | No |
| Semaphore | CI/CD runner | No |
| Vaultwarden | Password manager | No |
| Windmill | Workflow automation | No |

When any non-critical service misbehaves — exhausts memory, saturates disk I/O,
crashes the Docker daemon — the four identity-core services go down with it.
Because every published service depends on Keycloak for authentication, Step-CA
for TLS certificates, and OpenBao for runtime secrets, a single misbehaving
workload on this VM can cascade into a platform-wide outage.

The current monitoring interval for identity services is **60 seconds** in
Uptime Kuma, with no automated recovery. A dead Keycloak can sit unnoticed for
over a minute, and manual intervention is required to restart it.

This has happened repeatedly. It needs to stop.

## Decision

### 1. Strip `runtime-control-lv3` to identity-core only

`runtime-control-lv3` retains only the four identity-core services:

| Service | Port | Health Endpoint |
|---|---|---|
| Keycloak | 8091 (public), 18080 (local), 19000 (mgmt) | `http://127.0.0.1:19000/health/live` |
| Step-CA | 9000 | `https://127.0.0.1:9000/health` (TLS, ignore cert) |
| OpenBao | 8201 (HTTP), 8200 (TLS) | `http://127.0.0.1:8201/v1/sys/health` |
| API Gateway | 8083 | `http://127.0.0.1:8083/healthz` |

All other services are evicted to appropriate runtime VMs in a follow-up
workstream (not gated on this ADR):

| Service | Target VM | Rationale |
|---|---|---|
| Gitea | `docker-runtime-lv3` | Developer tooling, not identity |
| Harbor | `docker-runtime-lv3` | Container registry, not identity |
| Mail Platform | `runtime-general-lv3` | Communication, not identity |
| OpenFGA | `runtime-apps-lv3` | Authorization engine, app-tier |
| Temporal | `runtime-apps-lv3` | Workflow orchestration |
| Semaphore | `docker-build-lv3` | CI/CD belongs with build infra |
| Vaultwarden | `runtime-general-lv3` | User-facing password manager |
| Windmill | `runtime-apps-lv3` | Workflow automation, app-tier |

The eviction workstream is tracked separately. This ADR focuses on the watchdog
that protects whatever is currently running on `runtime-control-lv3`.

### 2. Deploy an aggressive identity-core health watchdog

A new Ansible role `identity_core_watchdog` installs a systemd timer on
`runtime-control-lv3` that runs every **15 seconds** and:

1. **Probes** each identity service health endpoint.
2. **Auto-restarts** any service whose health check fails via
   `docker compose restart <service>` (scoped to the failing stack only).
3. **Logs** every probe result to the systemd journal for Loki ingestion.
4. **Sends an ntfy notification** on failure detection and on recovery, so the
   operator is alerted immediately even if they are not watching dashboards.
5. **Writes a machine-readable status file** (`/var/lib/lv3-identity-watchdog/status.json`)
   for consumption by the API gateway health aggregate and Prometheus node
   exporter textfile collector.

### Watchdog contract

| Parameter | Value |
|---|---|
| Probe interval | 15 seconds |
| Probe timeout per service | 5 seconds |
| Consecutive failures before restart | 2 (30 seconds of downtime) |
| Max restarts per service per hour | 6 (prevents restart storms) |
| Notification channel | ntfy topic `platform-identity-critical` |
| Status file | `/var/lib/lv3-identity-watchdog/status.json` |
| Journal identifier | `lv3-identity-watchdog` |

### 3. Tighten Uptime Kuma monitoring intervals

Identity service monitors in Uptime Kuma are updated from 60-second to
**15-second** intervals:

- Keycloak OIDC Discovery: 60s → 15s
- Step CA Private: 60s → 15s
- Platform API Gateway Public: 60s → 15s (identity-adjacent)

This provides external validation alongside the on-VM watchdog.

## Places That Need to Change

### 1. New role: `roles/identity_core_watchdog/`

**What:** Create a new Ansible role that installs:
- `/usr/local/libexec/lv3-identity-watchdog.sh` — health check + auto-restart script
- `lv3-identity-watchdog.service` — systemd oneshot service
- `lv3-identity-watchdog.timer` — systemd timer (every 15s)
- `/var/lib/lv3-identity-watchdog/` — state directory

### 2. `config/health-probe-catalog.json`

**What:** Add an `identity_core_watchdog` entry documenting the on-VM watchdog
contract, and add a `watchdog` sub-key to keycloak, step_ca, openbao, and
api_gateway entries referencing the 15-second on-VM probe.

### 3. `config/uptime-kuma/monitors.json`

**What:** Update intervals for Keycloak, Step-CA, and API Gateway monitors
from 60s to 15s.

### 4. New playbook: `playbooks/services/identity-core-watchdog.yml`

**What:** Playbook that converges the `identity_core_watchdog` role on
`runtime-control-lv3`.

### 5. `config/ntfy/topic-registry.json`

**What:** Register the `platform-identity-critical` topic if not already present.

## Consequences

### Positive

- Identity services are detected as unhealthy within 15 seconds instead of 60.
- Auto-restart means most transient failures self-heal in under 45 seconds
  (2 failed probes + restart time) without operator intervention.
- The stripped VM has far less resource contention — only 4 lightweight services
  instead of 12.
- ntfy notifications provide immediate alerting even when dashboards are down.
- Machine-readable status file enables the API gateway to report identity health
  in its aggregate endpoint.

### Negative / Trade-offs

- The 15-second timer adds a small but constant CPU overhead on the VM (~0.1%).
- The restart-rate limiter (6/hour) means a service with a persistent failure
  will stop being restarted after ~10 minutes, requiring manual intervention.
- Evicting 8 services to other VMs is a multi-session effort tracked separately.

## Related ADRs

- ADR 0010: Initial Proxmox VM Topology
- ADR 0025: Compose-managed runtime stacks
- ADR 0056: Keycloak as platform session authority
- ADR 0101: Certificate lifecycle management (Step-CA)
- ADR 0204: Correction-loop policy
- ADR 0226: Systemd as host-resident supervisor
- ADR 0331: Runtime pool workload split (created runtime-control-lv3)
- ADR 0340: Dedicated Coolify apps VM separation (template for this pattern)
- ADR 0347: Docker runtime workload split
