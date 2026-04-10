# ADR 0400: Homepage Dashboard Fidelity — Catalog-Driven Lifecycle and UX Compliance

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.92
- Implemented In Platform Version: not yet applied
- Implemented On: 2026-04-10
- Date: 2026-04-10
- Concern: Platform, UX, Automation
- Depends on: ADR 0152 (Homepage Dashboard), ADR 0389 (Service Decommissioning), ADR 0399 (Reconciliation Daemon)
- Tags: homepage, dashboard, ux, selectability, catalog-fidelity, iac

---

## Context

### Stale entries after service removal

One-API (ADR 0393) and Open WebUI (ADR 0390) were fully removed from the
platform on 2026-04-10. Their entries were deleted from
`service-capability-catalog.json` and `subdomain-catalog.json`. However,
the live homepage at home.lv3.org still displays tiles for both services
because:

1. `generate_homepage_config.py` was not re-run after the catalog changes.
2. `make converge-homepage` was not invoked to push the new config to the
   runtime.
3. There is no automated reconciliation loop (addressed in ADR 0399).

This is the specific incident that motivates ADR 0399's reconciliation daemon,
but it also reveals gaps in the homepage's own fidelity contract.

### Open WebUI replaced by LibreChat

Open WebUI at `chat.lv3.org` has been replaced by LibreChat. The subdomain
catalog should reflect this. The homepage generator already handles this
correctly (it reads from the catalog), but only if the catalog is accurate
and the generator is re-run.

### Text not selectable in browser

Users report that text on home.lv3.org cannot be selected or copied. The
gethomepage/homepage application uses CSS that prevents text selection on
service cards and other elements. This is a UX regression — operators need
to copy service URLs, descriptions, and status information from the dashboard.

### Root cause analysis

The homepage uses a third-party container (gethomepage/homepage) that applies
`user-select: none` or equivalent pointer-events CSS to interactive card
elements. Our `custom.css` injection point (via `generate_homepage_config.py`)
can override this behavior.

---

## Decision

### 1. Fix text selectability via custom CSS

Add `user-select: text` overrides to the generated `custom.css` to ensure
all text content on the homepage is selectable:

```css
/* Ensure all text is selectable for operator copy-paste workflows */
*, *::before, *::after {
  -webkit-user-select: text !important;
  user-select: text !important;
}

/* Preserve pointer events on interactive elements */
a, button, input, [role="button"] {
  cursor: pointer;
}
```

This is implemented in `scripts/generate_homepage_config.py`'s
`build_custom_css()` function.

### 2. Homepage generation is the sole path to dashboard content

Reinforce the existing IaC principle: the homepage configuration is
**exclusively** generated from `service-capability-catalog.json` and
`subdomain-catalog.json`. No manual edits to the Homepage container's
config files are permitted.

The generation pipeline already enforces this:
- `generate_homepage_config.py --write` produces all config files.
- `generate_homepage_config.py --check` validates freshness.
- The Ansible role copies generated config into the container volume.

What was missing: **automated invocation**. ADR 0399 addresses this with
the reconciliation daemon.

### 3. Decommission procedure must trigger homepage reconvergence

Extend the service decommission checklist (ADR 0389) to include:

> After removing a service from catalogs, trigger portal reconciliation:
> `make reconcile-portals` or wait for the next 15-minute reconciliation cycle.

Until ADR 0399 is implemented, the manual step is:

```bash
python scripts/generate_homepage_config.py --output-dir build/homepage-config --write
make converge-homepage env=production
```

### 4. Catalog fidelity contract

The homepage generator MUST:

- **Include** every service with `lifecycle_status: "active"` and a
  browser-usable URL.
- **Exclude** every service with `lifecycle_status` != `"active"` (removed,
  deprecated, decommissioned).
- **Reflect** the current `public_url` from the catalog (e.g., `chat.lv3.org`
  now points to LibreChat, not Open WebUI).

The existing `include_service()` function in `generate_homepage_config.py`
already implements this contract. The bug was not in the code but in the
deployment pipeline — the code was not re-run.

### 5. Pre-push validation for homepage freshness

Add a `--check` validation step to the pre-push gate that verifies
`build/homepage-config/` matches the current catalog state:

```bash
python scripts/generate_homepage_config.py \
  --output-dir build/homepage-config --check
```

This ensures that catalog changes cannot be pushed without also regenerating
the homepage config.

---

## Consequences

### Positive

- **Text is copyable**: Operators can select and copy URLs, descriptions,
  and service names from the dashboard.
- **No stale tiles**: Removed services disappear from the dashboard within
  one reconciliation cycle (or immediately on manual converge).
- **IaC enforced**: The generation-only pipeline prevents config drift from
  manual edits.
- **Decommission completeness**: ADR 0389 now includes portal cleanup as
  an explicit step.

### Trade-offs

- **CSS override is broad**: The `user-select: text !important` rule overrides
  the upstream Homepage app's styling globally. If the app updates its CSS
  in a way that conflicts, the override may need adjustment. Acceptable
  because we pin the container image version.
- **Pre-push check adds ~2s**: The `--check` mode is fast (pure Python,
  no network calls) but adds to the gate duration. Negligible.

---

## Implementation

### Immediate (this branch)

1. Update `build_custom_css()` in `generate_homepage_config.py` to include
   text selectability rules.
2. Verify One-API and Open WebUI are absent from catalogs (confirmed: already
   removed in ADRs 0390/0393).
3. Document the reconvergence step in the decommission runbook.

### Follow-up (ADR 0399)

1. Automated reconciliation loop regenerates and deploys homepage config.
2. Pre-push gate validates homepage config freshness.
3. Health sweep verifies live portal content matches catalog.

---

## Related

- ADR 0152: Homepage for Unified Service Dashboard
- ADR 0389: Standard Procedure for Decommissioning a Platform Service
- ADR 0390: Remove Open WebUI from the Platform
- ADR 0393: Remove One-API from the Platform
- ADR 0399: Platform Reconciliation Daemon (companion ADR)
