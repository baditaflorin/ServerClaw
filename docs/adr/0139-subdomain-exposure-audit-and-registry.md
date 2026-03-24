# ADR 0139: Subdomain Exposure Audit and Registry

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.127.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

`config/subdomain-catalog.json` (ADR 0076) is the declared inventory of governed `lv3.org` hostnames. Before this ADR, the repository could validate basic catalog structure and edge-route coverage, but it still lacked a dedicated exposure view that answered four operator questions quickly and deterministically:

1. Which tracked hostnames are actually active today?
2. Which hostnames are intentionally public, edge-authenticated, upstream-authenticated, or private-only?
3. Which repo-managed edge routes exist without a matching catalog classification?
4. Which production hostnames already resolve publicly even though the catalog still treats them as not live?

That gap creates a drift window. A hostname can move from "planned" to publicly reachable, or from "auth-gated" to anonymously reachable, without a single derived surface making the discrepancy obvious during review.

On 2026-03-24, live DNS verification showed that `ops.lv3.org`, `docs.lv3.org`, and `changelog.lv3.org` already resolved publicly while the catalog still marked them `planned`. The repository needed a durable registry and an audit step that could detect exactly that class of mismatch.

## Decision

We will maintain a **deterministic subdomain exposure registry** generated from:

- `config/subdomain-catalog.json`
- `inventory/host_vars/proxmox_florin.yml`
- `roles/nginx_edge_publication/defaults/main.yml`

and pair it with a **subdomain exposure audit** that can check live DNS and edge-auth behavior.

### Registry contract

The generated registry lives at `config/subdomain-exposure-registry.json`. Each entry records:

- the catalog identity: `fqdn`, `service_id`, `environment`, `status`, `owner_adr`
- the exposure model: `exposure`, `auth_requirement`
- the expected network path: `target`, `target_port`, `dns_record_type`
- the repo-managed route state: `route_mode`, `route_source`, `route_kind`, `edge_auth`
- whether production live tracking is expected right now

### Auth requirement classification

The catalog now requires one `auth_requirement` value per hostname:

- `none`: intentionally unauthenticated public or informational edge surface
- `edge_oidc`: authentication is enforced at the shared nginx edge through `oauth2-proxy`
- `upstream_auth`: authentication is handled by the upstream application rather than the shared edge
- `private_network`: the hostname is intentionally private and must not be published on the public edge

Repository validation rejects:

- any missing `auth_requirement`
- any private-only hostname that is not `private_network`
- any active `edge_oidc` hostname missing repo-managed edge protection
- any mismatch between `public_edge_authenticated_sites` and the catalog classification for an active edge route

### Audit checks

The audit script performs four classes of checks:

1. **Repo contract check**
   - Compare catalog `auth_requirement` values to repo-managed edge auth wiring.
   - Emit a CRITICAL finding if an active `edge_oidc` hostname is not protected by `oauth2-proxy`.

2. **Live DNS resolution check**
   - Resolve production hostnames that should already be active.
   - Emit a CRITICAL finding when a hostname resolves publicly to the expected target but is not tracked as `active`.
   - Emit a WARN finding when an `active` hostname no longer resolves as expected.

3. **Live edge-auth probe**
   - For active `edge_oidc` hostnames, make an unauthenticated HTTPS request.
   - Emit a CRITICAL finding if the request does not redirect into the Keycloak authorization flow at `sso.lv3.org`.

4. **Hetzner DNS zone check**
   - When `HETZNER_DNS_API_TOKEN` is available, enumerate the full Hetzner DNS zone.
   - Emit a CRITICAL finding for undeclared A/AAAA/CNAME records present in the zone.
   - Emit a WARN finding when a zone record differs from the catalog target or type.

### Automation surface

Repository implementation includes:

- `scripts/subdomain_exposure_audit.py`
- `config/windmill/scripts/subdomain-exposure-audit.py`
- `make subdomain-exposure-audit`
- `docs/runbooks/subdomain-exposure-audit.md`
- `receipts/subdomain-exposure-audit/`

This is sufficient for repository implementation. Scheduling the worker wrapper weekly and wiring any downstream notification hooks still requires apply from `main`.

## Consequences

### Positive

- Publicly reachable but misclassified hostnames are detected from repository validation and audit receipts instead of operator memory.
- The auth model for each hostname is explicit and reviewable.
- The derived registry provides one stable machine-readable surface for portals, operators, and later automation.

### Negative / Trade-offs

- The registry duplicates information already present in the canonical catalog and edge defaults, so it must stay generated rather than hand-maintained.
- Full shadow-subdomain detection depends on the Hetzner DNS API token being available to the audit runtime.
- This ADR records current exposure accurately; it does not itself harden public portals that remain intentionally unauthenticated today.

## Boundaries

- This ADR covers `lv3.org` hostnames tracked in the governed subdomain catalog.
- It does not replace separate hardening ADRs that change whether a given portal should be public.
- It does not auto-remediate DNS or edge-auth drift.

## Implemented Outcome

- The repository now ships the canonical registry at `config/subdomain-exposure-registry.json`, the audit tool at `scripts/subdomain_exposure_audit.py`, the worker wrapper at `config/windmill/scripts/subdomain-exposure-audit.py`, and the operator workflow in `docs/runbooks/subdomain-exposure-audit.md`.
- `config/subdomain-catalog.json` now records `auth_requirement` for every tracked hostname.
- Production entries for `ops.lv3.org`, `docs.lv3.org`, and `changelog.lv3.org` were corrected to `status: active` after live DNS verification on 2026-03-24.

## Related ADRs

- ADR 0076: Subdomain governance and DNS lifecycle
- ADR 0091: Continuous drift detection
- ADR 0093: Interactive ops portal
- ADR 0094: Developer portal and documentation site
