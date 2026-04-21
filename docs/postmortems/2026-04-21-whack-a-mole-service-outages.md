# Post-Mortem: Whack-a-Mole Service Outages (2026-04-21)

**Date:** 2026-04-21
**Duration:** Ongoing / systemic (multiple incidents over 6 weeks)
**Severity:** Medium–High (individual service outages, no platform-wide failure)
**Status:** Remediation in progress — ADR 0421 + `platform_service_watchdog` role

---

## Executive Summary

Over the six weeks since the LV3 platform reached ~73 deployed services, a
recurring operational pattern emerged: a service goes down, an operator or user
notices, the service is manually restarted, and within a few days a different
service is down again. This is the "whack-a-mole" pattern.

No single incident was catastrophic. But the aggregate time spent on manual
restarts, the latency between failure and detection, and the lack of a
systematic fix made this a chronic reliability drag.

This postmortem captures the pattern, its root causes, and the remediations
implemented in ADR 0421.

---

## Representative Incidents

| Date | Service | Cause | Time to Detect | Recovery |
|------|---------|-------|----------------|----------|
| 2026-04-05 | Outline | OOM kill — container ran out of RAM | ~15 min (Uptime Kuma) | Manual `docker compose restart` |
| 2026-04-07 | Keycloak | OpenBao sealed after VM reboot; Keycloak couldn't fetch secrets | ~8 min | Manual openbao unseal + keycloak restart |
| 2026-04-09 | Harbor | Docker daemon restart cleared container state | ~30 min (user report) | `docker compose up -d` |
| 2026-04-10 | NetBox | Postgres connection pool exhausted | ~5 min (Uptime Kuma) | `docker compose restart netbox` |
| 2026-04-12 | Langfuse | Image OOM-killed; compose had no restart policy | ~20 min (user report) | Added `restart: unless-stopped` + restart |
| 2026-04-14 | Semaphore | Crash loop due to misconfigured Keycloak OIDC redirect | ~10 min | Fixed env var + restart |
| 2026-04-15 | Grist | Container stopped for unknown reason | ~25 min (user report) | Manual restart |
| 2026-04-18 | Matrix Synapse | SQLite journal lock after ungraceful stop | ~45 min | Journal repair + restart |
| 2026-04-20 | Mattermost | Ran out of disk space on docker-runtime | ~1h (user report) | Cleared logs + restart |
| 2026-04-21 | Multiple | No platform-wide watchdog deployed | Ongoing | ADR 0421 initiated |

---

## Root Cause Analysis

### RC-1: No automated service recovery (highest impact)

The identity_core_watchdog (ADR 0376) covered 5 services on runtime-control.
No equivalent existed for the other 68 services on 5 VMs.

When a service stopped:
- Uptime Kuma would alert **after 60 seconds** (configurable but default)
- The alert notified a human
- A human SSH'd in and ran `docker compose restart`
- Total time from failure to recovery: **5–60 minutes** depending on operator availability

There was no automated restart path for any non-identity service.

### RC-2: Incomplete `restart: unless-stopped` coverage in compose stacks

Docker Compose restart policies prevent stopped containers from staying stopped
across daemon restarts and after OOM kills. At the time of these incidents,
~40% of docker-runtime services lacked an explicit `restart:` policy in their
compose stacks.

The `derive_service_defaults.yml` macro now adds `restart: unless-stopped` for
all services (ADR 0368), but this was not uniformly applied before that.

**Why containers stopped despite `restart: unless-stopped`:**
- OOM kill: `restart: unless-stopped` does restart OOM-killed containers, but
  if the root cause (memory pressure) persists, the container enters a crash
  loop. This is correct behavior — a watchdog should detect the loop and alert.
- Daemon restart: All services with `restart: unless-stopped` restart after
  Docker daemon restarts. Services without the policy do not.
- User-initiated stop (`docker stop`): `unless-stopped` respects manual stops.
  This is a footgun — operators stopping one container for maintenance
  sometimes stopped the wrong one or forgot to restart it.

### RC-3: Uptime Kuma coverage gap

25 of 73 services were not in Uptime Kuma at all:
- Private-only services (alertmanager, internal APIs)
- Services behind OIDC (coolify, outline from an external perspective)
- Services with internal-only ports

For these services, failure was detected only when a user reported it.

### RC-4: Detection latency too high for identity-critical services

Keycloak going down for 1 minute breaks every OIDC login on the platform.
A 60-second Uptime Kuma check means up to 2 minutes of undetected downtime.

ADR 0376 defined a 15-second identity watchdog but was marked "Not Implemented"
even though the role code was deployed (the ADR status was stale). The
`identity_core_watchdog` defaults were actually running at **30 seconds**,
not 15 as the ADR specified.

### RC-5: Monitoring stack itself unmonitored

Alertmanager, Grafana, and Prometheus were not in Uptime Kuma. If the
monitoring stack went down, outage alerts would silently stop. This was
discovered only when Grafana dashboards became stale.

### RC-6: No structured escalation after failed restarts

When a service restarted but kept crashing (crash loop), there was no automatic
escalation path. The watchdog would hit its 6/hour restart limit and stop
trying, but the operator was only notified at the time of hitting the limit —
not with increasing urgency as the situation persisted.

---

## What Worked

- **Uptime Kuma** caught 60% of incidents within 5 minutes for monitored services.
- **ntfy** push notifications reached the operator even outside working hours.
- **docker compose restart** was consistently effective for transient failures.
- **ADR 0346 health gates** prevented compose stacks with unhealthy dependencies
  from masking root causes.
- **Loki log retention** allowed post-incident analysis even when no one was
  watching the dashboards at the time.

---

## Remediation

### Immediate (ADR 0421 — this workstream)

1. **Deploy `platform_service_watchdog` to all 6 application VMs**
   - Covers 57 HTTP-probed services (up from 5 with identity watchdog)
   - 30-second probe interval (down from 60s Uptime Kuma)
   - 2 consecutive failures → `docker compose restart` (automatic)
   - 6 restarts/hour/service rate limit with ntfy escalation

2. **Mark OpenBao as `exclude_from_auto_restart: true`**
   - OpenBao restart without unseal key shares leaves it sealed
   - Watchdog probes and alerts but does not restart it
   - Operator must unseal manually (or configure auto-unseal, tracked in separate workstream)

### Short-term (within 2 weeks)

3. **Fix ADR 0376 implementation status** — update ADR to "Implemented", confirm
   the systemd timer is active on runtime-control, validate the 30-second interval

4. **Add Alertmanager + Grafana to Uptime Kuma** — the monitoring stack must
   itself be monitored

5. **Audit `restart: unless-stopped` coverage** — run
   `grep -r "restart:" roles/*/templates/docker-compose*.j2` and ensure all
   app services have an explicit restart policy

6. **Document OpenBao auto-unseal as P1 workstream** — the most impactful
   single improvement to platform resilience: auto-unseal means no manual
   intervention needed after VM reboots

### Medium-term (within 1 month)

7. **Implement ADR 0376 Phase 3 escalation** — after 3 restart cycles in 1
   hour, create a Plane issue (ADR 0360) for human triage. Prevents operators
   from missing stuck crash loops.

8. **Implement ADR 0358 health contract** — upstream health prerequisites
   before service applies. A service should not be started if its dependencies
   (OpenBao, Keycloak, Postgres) are not healthy.

9. **Add watchdog status feeds to Grafana** — each VM's watchdog writes a
   status JSON; pipe this into the composite health index (ADR 0128) and
   Grafana dashboard.

10. **Per-service restart budget tracking in Plane** — when a service exceeds
    its hourly restart budget, auto-create a Plane issue with the log tail
    attached.

---

## Lessons Learned

### 1. Detection ≠ Recovery

Having Uptime Kuma alert on a down service is not a recovery plan. Every
detected failure that required manual restart was a missed automation
opportunity. **The gap between "alert" and "recovery" must be filled by code.**

### 2. Coverage compounds

Missing 25/73 services from Uptime Kuma meant that for those services, the
first detection signal was a user complaint. User-reported outages have
systematically longer time-to-detect than automated monitoring. **Every service
that touches production traffic must have at least one automated probe.**

### 3. The identity watchdog pattern scales

The `identity_core_watchdog` role (ADR 0376) proved the pattern works. It's
been running on runtime-control without incident. The right move was to
generalize it immediately rather than treating it as a one-off. **Good
operational patterns should be platform defaults, not exceptions.**

### 4. Restart budgets prevent storms but not crash loops

A restart budget (6/hour) prevents a single bad service from consuming all
available Docker restart bandwidth. But it means a service in a crash loop
goes dark after an hour. **Restart budgets need escalation paths, not just
rate limits.**

### 5. OpenBao is a single point of failure for restart recovery

If OpenBao is sealed (after VM reboot without auto-unseal), every service that
reads secrets at startup fails to start. This creates a sequential dependency:
unseal OpenBao → start api-gateway → start other services. Without auto-unseal,
a VM reboot requires operator intervention before anything else can recover.
**Auto-unseal (Shamir split + HA or cloud KMS wrapper) is the correct fix.**

### 6. Monitoring the monitoring stack is not optional

An unmonitored alertmanager is worse than no alertmanager — it creates false
confidence. **The monitoring stack (alertmanager, grafana, prometheus, loki)
must be the first thing in Uptime Kuma, not an afterthought.**

---

## Action Items

| Priority | Item | Owner | ADR / Ticket | Due |
|----------|------|-------|--------------|-----|
| P0 | Deploy platform_service_watchdog to all VMs | Platform | ADR 0421 | 2026-04-22 |
| P0 | Validate identity_core_watchdog is active on runtime-control | Platform | ADR 0376 | 2026-04-21 |
| P1 | Add alertmanager + grafana to Uptime Kuma | Platform | — | 2026-04-23 |
| P1 | Audit restart: unless-stopped coverage | Platform | ADR 0368 | 2026-04-24 |
| P1 | Document OpenBao auto-unseal as P1 workstream | Platform | New ADR | 2026-04-25 |
| P2 | Implement escalation after restart budget exhausted | Platform | ADR 0421 Phase 3 | 2026-05-05 |
| P2 | Watchdog status feeds into composite health index | Platform | ADR 0128 | 2026-05-10 |
| P2 | ADR 0358 health contract implementation | Platform | ADR 0358 | 2026-05-15 |

---

## Metrics: Before vs. After (Target)

| Metric | Before ADR 0421 | Target After |
|--------|-----------------|--------------|
| Services with auto-recovery | 5 (identity only) | 57 (all HTTP-probed) |
| Mean time to detect (MTTD) | 5–60 min | < 60 seconds |
| Mean time to recover (MTTR) automated | N/A | < 90 seconds |
| Operator interventions per week | ~3 | < 1 |
| Services with Uptime Kuma coverage | 48/73 (66%) | 73/73 (100%) |
