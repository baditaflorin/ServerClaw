# ADR 0421: Platform-Wide Service Watchdog

- Status: Accepted
- Implementation Status: Partial
- Date: 2026-04-21
- Concern: monitoring, resilience, automation
- Tags: watchdog, health, service-recovery, systemd, docker-compose, uptime
- Depends on: ADR 0376 (Identity Core Watchdog), ADR 0226 (Systemd Timers), ADR 0064 (Health Probe Catalog), ADR 0123 (Liveness and Readiness Contracts), ADR 0399 (Platform Reconciliation Daemon)

---

## Context

### The whack-a-mole problem

Over the six weeks since the platform reached ~73 deployed services, a recurring
operational pattern has emerged: a service goes down, an operator notices (via
Uptime Kuma alert, a failed user request, or manual inspection), and manually
restarts it. The next day, a different service is down. Repeat indefinitely.

Root causes identified across incidents:

| Cause | Frequency | Example |
|-------|-----------|---------|
| Docker container OOM-killed | High | Langfuse, Outline, NetBox |
| Docker daemon restart wipes compose state | Medium | All docker-runtime services after VM reboot |
| Compose health check never declared → no `depends_on: condition: service_healthy` | Medium | Woodpecker, Dify |
| Service crashes silently (no restart policy in compose) | Medium | Matrix Synapse, Mattermost |
| OpenBao sealed after host reboot → dependent services fail to start | High | api-gateway, gitea, all OIDC clients |
| Step-CA TLS cert expiry → health probes fail, no auto-recovery | Low | step-ca → keycloak → everything |

### Why Uptime Kuma alone is insufficient

- **Check interval**: 60 seconds by default. A dead Keycloak (which breaks every
  OIDC login on the platform) can sit undetected for a full minute.
- **No remediation**: Uptime Kuma alerts but cannot restart services.
- **Coverage gap**: 25/73 services skip Uptime Kuma entirely (private endpoints,
  internal services, OIDC-gated dashboards).
- **External perspective only**: Uptime Kuma checks from outside the host;
  container-level restart logic needs to run on the VM itself.

### What ADR 0376 gave us — and what it missed

ADR 0376 deployed an aggressive watchdog for the four identity-core services
(Keycloak, Step-CA, OpenBao, API Gateway) on `runtime-control`. The pattern
works well:

- 30-second probe interval via systemd timer
- 2 consecutive failures → auto-restart via `docker compose restart`
- 6 restarts/hour rate limit to prevent storms
- ntfy notifications on failure and recovery

**Gap**: The pattern covers only 5 services on 1 VM. The remaining 68+ services
on 6 other VMs have no equivalent protection.

### Current monitoring stack summary

| Tool | Coverage | Auto-Recovery |
|------|----------|---------------|
| Uptime Kuma | 48/73 services, 60s intervals | No |
| Portal health sweep (ADR 0399) | 4 portals, 60 min | No |
| Composite health index (ADR 0128) | 73 services, per-minute | No |
| Identity watchdog (ADR 0376) | 5 services on runtime-control | Yes |
| Docker compose health checks (ADR 0346) | Dependency gates only | Partial |

**The coverage-vs-recovery matrix has exactly one cell filled.** The other
68+ services alert (at best) but never self-heal.

---

## Decision

### Extend the identity watchdog pattern to every VM

Deploy a `platform_service_watchdog` role to every VM that runs application
services. The role installs a systemd timer that:

1. **Probes** each service's HTTP health endpoint (from `health-probe-catalog.json`)
   every **30 seconds**.
2. **Auto-restarts** via `docker compose restart` after **2 consecutive failures**.
3. **Rate-limits** restarts to **6 per service per hour** to prevent storms.
4. **Alerts** via ntfy on failure, on restart, on recovery, and on rate-limit hit.
5. **Writes** a machine-readable status file consumed by the composite health index.
6. **Logs** every probe to systemd journal (→ Loki ingestion, ADR 0052).

### VM deployment matrix

| VM | Services watched | Priority |
|----|-----------------|----------|
| `runtime-control` | keycloak, step-ca, openbao, api-gateway, harbor, gitea, mail_platform, temporal, windmill, semaphore, openfga | P0 — identity-critical (extends ADR 0376) |
| `docker-runtime` | browser_runner, changedetection, crawl4ai, dify, directus, dozzle, glitchtip, grist, label_studio, lago, langfuse, litellm, matrix_synapse, mattermost, minio, n8n, netbox, ntfy, ollama, outline, paperless, piper, plane, plausible, repowise, searxng, superset, typesense, woodpecker | P1 — app services |
| `runtime-general` | homepage, mailpit, uptime_kuma | P1 — platform ops |
| `runtime-ai` | gotenberg, tesseract_ocr, tika | P2 — AI processing |
| `monitoring` | alertmanager, grafana | P1 — observability pipeline |
| `coolify` | coolify, librechat | P2 — managed deployments |

### Probe strategy

Only HTTP services with a `liveness.kind: http` entry in `config/health-probe-catalog.json`
get probed by the watchdog. TCP and command-based probes are out of scope
(handled by Docker's own health checks via `condition: service_healthy`).

For services without an HTTP health endpoint, the watchdog falls back to
`docker inspect --format '{{.State.Health.Status}}'` when a container name
is provided.

### Service exclusions

Services excluded from watchdog auto-restart:

| Service | Reason |
|---------|--------|
| `openbao` | Unsealing after restart requires manual Shamir key shares or auto-unseal config |
| `postgres` | Database restarts must be operator-verified to avoid split-brain |
| `nginx_edge` | Systemd unit, not Docker |

These services are still **probed** and **alerted** on failure; only the
auto-restart is suppressed.

### Ansible role: `platform_service_watchdog`

New role. Parameterized by:

- `service_watchdog_name` — logical name for this watchdog instance (default: `platform`)
- `service_watchdog_services` — list of service probe definitions (see schema below)
- `service_watchdog_probe_interval_sec` — probe interval (default: 30)
- `service_watchdog_failure_threshold` — consecutive failures before restart (default: 2)
- `service_watchdog_max_restarts_per_hour` — restart rate limit (default: 6)
- `service_watchdog_ntfy_url` — ntfy base URL
- `service_watchdog_ntfy_topic` — ntfy topic (default: `platform-service-watchdog`)

Service probe schema (mirrors the identity watchdog service spec):

```yaml
- name: dify
  compose_dir: /opt/dify
  compose_service: api
  restart_args: ""                 # empty = restart; "up -d" for stopped containers
  health_url: "http://127.0.0.1:8094/healthz"
  health_method: ""                # curl flags, e.g. "-k" for TLS
  expected_status: "200"
  exclude_from_auto_restart: false # set true for openbao, postgres
```

### Postmortem and learned lessons

See `docs/postmortems/2026-04-21-whack-a-mole-service-outages.md`.

---

## Consequences

### Positive

- Every VM-resident HTTP service has a 30-second recovery path from transient failure.
- Platform-wide restart budget (6/hour/service) prevents cascading restart storms.
- ntfy alerts close the gap between failure and operator awareness from
  up to 60 seconds → reliably under 60 seconds.
- Machine-readable status files feed the composite health index (ADR 0128)
  and Grafana dashboards without Uptime Kuma dependency.
- The watchdog's systemd journal output feeds Loki (ADR 0052) — all probe
  results are queryable and alertable via Grafana Alertmanager.

### Negative / trade-offs

- Adds a systemd timer and script to every application VM. This is intentional
  but adds surface area to audit.
- 30-second probe interval × 73 services × 6 VMs = ~438 HTTP requests every
  30 seconds on the internal network. Negligible but measurable.
- Services that are unhealthy for structural reasons (misconfigured env, missing
  secret) will hit the 6/hour restart limit and require manual investigation.

### Open items

- [ ] Phase 2: Extend probe to `docker inspect` health status for services
      without HTTP endpoints
- [ ] Phase 3: Structured escalation — after 3 restart cycles in 1 hour, create
      a Plane issue (ADR 0360) for human triage
- [ ] Phase 4: Watchdog health is itself monitored — deploy a Loki alert rule
      that fires if the watchdog hasn't emitted a log line in >2 minutes

---

## Implementation Notes

### Deployment order

1. `runtime-control` first (identity-core — extends existing ADR 0376 watchdog)
2. `docker-runtime` second (highest service density, most incidents)
3. All other VMs in parallel

### Makefile target

```bash
make converge-platform-watchdog env=production
```

Runs `playbooks/platform-service-watchdog.yml` across all VMs in dependency order.

### Runbook

See `docs/runbooks/platform-service-watchdog.md` (created alongside this ADR).
