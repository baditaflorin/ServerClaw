# Postmortem: Keycloak PostgreSQL pg_hba.conf Drift (2026-04-14)

**Date:** 2026-04-14
**Duration:** ~1 hour (from user report to full resolution)
**Severity:** P1 — All SSO-protected services inaccessible for new logins
**Status:** Resolved
**ADR:** ADR 0416 — Topology Consistency Enforcement

---

## Summary

After migrating Keycloak from `docker-runtime` to `runtime-control` (previous session),
the PostgreSQL `pg_hba.conf` still only allowed connections from the old host IP
(`10.10.10.20`). Keycloak on `runtime-control` (`10.10.10.92`) was blocked at the
database layer on every request, causing all authentication flows to fail with
"An internal server error has occurred."

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 2026-04-13 ~22:00 | Keycloak migrated from docker-runtime to runtime-control; nginx upstream hotfixed and converged |
| 2026-04-14 (morning) | User attempts SSO login at `chat.example.com` |
| 2026-04-14 | User reports: `sso.example.com` returns "An internal server error has occurred" with a Keycloak error page |
| +5 min | Investigation: Keycloak container status checked — `Up 35 hours (healthy)` — container is running |
| +8 min | Keycloak logs examined: `FATAL: no pg_hba.conf entry for host "10.10.10.92", user "keycloak", database "keycloak", SSL encryption` |
| +10 min | Root cause identified: `platform_postgres_clients.keycloak.source_vm` still set to `docker-runtime` |
| +12 min | Fix committed: `source_vm` changed to `runtime-control` in `platform_postgres.yml`; pushed to origin |
| +15 min | `make converge-postgres-vm env=production` run; `pg_hba.conf` updated (`changed=2`) |
| +17 min | Keycloak container restarted to clear failed connection pool |
| +18 min | Verification: `lv3` realm reachable, `serverclaw` client present, admin auth working |
| +20 min | Chat login confirmed working |

---

## Root Cause

### Primary: No cross-registry consistency check

The platform records "which VM runs this service" in four independent places:

1. `platform_service_registry.host_group` (deployment target for Ansible)
2. `lv3_service_topology[s].owning_vm` (nginx upstream routing)
3. `platform_postgres_clients[s].source_vm` (pg_hba.conf IP allow-list)
4. Generated `platform.yml` (derived connection strings)

When Keycloak moved to `runtime-control`:
- Places 2 and 4 were updated (fixing the nginx routing — ADR 0413 session)
- Places 1 and 3 were NOT updated (forgotten)

There was no automated check to catch this. The discrepancy sat undetected
until the first post-migration SSO attempt.

### Secondary: pg_hba.conf IP allow-list is security-critical but silently fails

When PostgreSQL rejects a connection via `pg_hba.conf`, the error appears only
in application logs — not in a health check, not in any monitoring alert.
Keycloak's health endpoint reports `healthy` even when all requests fail at the
DB layer. This masked the incident until a user attempted login.

### Contributing: No VM migration runbook existed

There was no documented checklist for "moving a service from one VM to another."
The engineer performing the Keycloak migration updated the places they knew about
but had no way to discover the full set of registries that needed updating.

---

## Resolution

1. **Immediate:** Changed `platform_postgres_clients.keycloak.source_vm` from
   `docker-runtime` to `runtime-control` in `inventory/group_vars/platform_postgres.yml`
2. **Applied:** Ran `make converge-postgres-vm env=production` — pg_hba.conf regenerated
   with `host keycloak keycloak 10.10.10.92/32 scram-sha-256` entry added
3. **Cleared:** Restarted `keycloak-keycloak-1` container to flush failed connection pool
4. **Verified:** SSO login working at `chat.example.com`

---

## Audit Findings

Running the new `validate_topology_consistency.py` tool immediately after this incident
revealed **20 topology drifts** across the platform — meaning the Keycloak case was
not unique. Seven more services had stale `host_group` entries in `platform_service_registry`:

```
keycloak, gitea, openfga, temporal, vaultwarden, windmill, openbao
```

All were corrected in the same session. Six additional topology-only drifts remain
pending human verification (see ADR 0416).

This confirms the pattern: **topology drift accumulates silently and only surfaces
when a downstream system enforces the stale value.**

---

## Action Items

| Item | Owner | Status | ADR |
|------|-------|--------|-----|
| Write cross-registry topology validator | Engineering | ✅ Done | ADR 0416 |
| Add validator to pre-push gate | Engineering | ✅ Done | ADR 0416 |
| Fix 7 stale `host_group` entries in registry | Engineering | ✅ Done | ADR 0416 |
| Fix `platform_postgres_clients.keycloak.source_vm` | Engineering | ✅ Done | — |
| Document VM migration runbook | Engineering | ✅ Done (in ADR 0416) | ADR 0416 |
| Verify 6 remaining topology drifts (uptime_kuma, mail_platform, redpanda, gotenberg, ollama, piper) | Operator | ⬜ Pending | ADR 0416 |
| Add DB connection failure alert to Keycloak monitoring | Engineering | ⬜ Pending | — |
| Phase 2: derive source_vm from host_group automatically | Engineering | ⬜ Planned | ADR 0416 |

---

## What Went Well

- **Fast detection:** User reported within hours of the Keycloak migration completing
- **Fast diagnosis:** Log inspection immediately revealed the pg_hba.conf error
- **Clean fix:** Single-line change + converge + restart — no data loss, no extended outage
- **Leverage:** The incident motivated building a validator that found 20 more latent drifts

## What Went Poorly

- **Silent health check:** Keycloak reported `healthy` while all DB operations failed
- **No migration checklist:** The engineer knew to update nginx but not postgres
- **Drift accumulation:** 20 drifts existed; this is the third drift incident in 72h
- **Detection gap:** Drift existed from the moment of migration (~22:00) but wasn't
  caught until a user tried to log in (~8h later)

## Lessons Learned

1. **Every registry that encodes VM assignment is a correctness invariant**, not just
   documentation. All must be kept in sync or the platform behaves incorrectly.

2. **Application health endpoints that don't test the DB layer are misleading.** A service
   that can't connect to its database is not healthy. Health checks must exercise the DB path.

3. **Drift compounds.** Three topology drift incidents in 72 hours means this is a systemic
   gap, not a one-off mistake. The fix must be systemic (gate enforcement), not procedural.

4. **The authoritative source needs to be declared.** Before this ADR, no document said
   which registry "wins" when they disagree. Now `platform_service_registry.host_group` is
   declared authoritative and machine-enforced.

---

## Prevention

This class of incident is now prevented by the pre-push gate running
`scripts/validate_topology_consistency.py --check`. Any future migration that
updates `host_group` without updating `source_vm` will be rejected at push time
before reaching production.

The long-term fix (ADR 0416 Phase 2) eliminates `source_vm` entirely by deriving
it from `host_group` at Ansible play time, making the drift impossible by construction.
