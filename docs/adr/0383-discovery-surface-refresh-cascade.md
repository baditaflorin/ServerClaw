# ADR 0383: Discovery Surface Refresh Cascade

- **Status:** Accepted
- **Implementation Status:** Implemented
- **Date:** 2026-04-08
- **Author:** LV3 Platform

## Context

The platform maintains multiple operator-facing discovery surfaces:

| Surface | URL | Source | Update Mechanism |
|---------|-----|--------|-----------------|
| Homepage | home.example.com | service-capability-catalog.json | converge-homepage playbook |
| Ops Portal | ops.example.com | service-capability-catalog.json | converge-ops-portal playbook |
| Wiki | wiki.example.com | docs/adr/*.md, docs/runbooks/*.md | sync_docs_to_outline.py |
| Platform Manifest | build/platform-manifest.json | Multiple catalogs | platform_manifest.py |

These surfaces share a common data source (the service catalog and ADR corpus) but
each requires its own explicit convergence run.  When a new service is deployed
(e.g., Neko at browser.example.com), the service catalog is updated but the downstream
surfaces are not refreshed.  This creates **drift** where operators see stale
service listings and missing ADRs.

### Observed drift (2026-04-08)

- browser.example.com (neko) deployed but absent from home.example.com and ops.example.com
- wiki.example.com missing approximately 60 ADRs (last synced around ADR 0320)
- Platform manifest timestamps stale

### Root cause

The convergence pipeline is **push-based and manual**.  Each surface is a separate
Make target and playbook.  No mechanism triggers downstream refreshes when the
service catalog or ADR corpus changes.

## Decision

Introduce a **refresh-discovery-surfaces** playbook and Make target that acts as
the single cascade entry point.  After any service deployment, operators (or
automation) invoke one command to propagate changes to all discovery surfaces.

### Cascade phases

```
Phase 0 (local):   Regenerate platform-manifest.json and discovery artifacts
Phase 1 (local):   Sync ADRs + docs to Outline wiki (wiki.example.com)
Phase 2 (remote):  Converge homepage (home.example.com on runtime-general)
Phase 2 (remote):  Converge ops portal (ops.example.com on docker-runtime)
Phase 2 (remote):  Refresh NGINX edge configs
```

### Usage

```bash
# Full refresh (all surfaces)
make refresh-discovery-surfaces env=production

# With trigger attribution (for audit trail)
make refresh-discovery-surfaces env=production trigger_service=neko

# Selective refresh (skip surfaces that don't need updating)
make refresh-discovery-surfaces env=production refresh_outline=false
```

### Integration into service playbooks

Service playbooks can import the cascade as a post-deploy step:

```yaml
# In a service playbook's final play:
- import_playbook: refresh-discovery-surfaces.yml
  vars:
    trigger_service: neko
  tags:
    - discovery
```

Operators who want to skip the cascade during iterative development can use
`--skip-tags discovery`.

### Evolution path

| Phase | Trigger | Mechanism |
|-------|---------|-----------|
| **Now** | Manual `make` target | Operator runs after deploy |
| **Near-term** | Gitea post-receive hook | Webhook triggers Semaphore job template |
| **Future** | NATS event bus | `platform.deploy.*` event triggers subscriber |

The `tasks/notify.yml` already publishes NATS events after each playbook.
A NATS consumer that listens for deploy events and invokes the refresh playbook
completes the event-driven architecture without changing the playbook structure.

## Consequences

### Positive

- Single command eliminates multi-surface drift
- Selective toggles avoid unnecessary convergence during development
- Audit trail via `trigger_service` parameter
- Compatible with future event-driven triggers (NATS, webhooks)
- Idempotent: safe to run repeatedly or on a cron schedule

### Negative

- Full cascade takes several minutes (homepage + ops portal convergence)
- Adds operational overhead if wired into every service playbook by default
- Outline sync requires API token (`.local/outline/api-token.txt`)

### Risks

- Ops portal generation currently fails if health probe catalog diverges from
  service catalog (pre-existing issue; not introduced by this ADR)
- Running the cascade during a service deploy extends the deploy window

## Related ADRs

- ADR 0074: Platform Operations Portal
- ADR 0093: Interactive Ops Portal
- ADR 0113: World State Materializer
- ADR 0152: Homepage Service Dashboard
- ADR 0199: Outline Living Knowledge Wiki
- ADR 0380: Neko Remote Desktop (triggered this ADR's creation)
