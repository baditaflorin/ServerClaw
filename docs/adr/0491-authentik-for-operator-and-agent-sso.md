# ADR 0491: Authentik For Operator And Agent SSO

- Status: Accepted
- Implementation Status: Live applied; repository integration is ready for release merge
- Implemented In Repo Version: 0.179.46
- Implemented In Platform Version: not yet
- Implemented On: 2026-08-31
- Date: 2026-08-27

## Context

ADR 0056 selected Keycloak as the shared SSO and identity-broker layer for internal operator-facing and approved agent-facing applications. Its own Vendor Exit Plan names the trigger for this ADR directly:

> Reevaluation Triggers: unacceptable upgrade or recovery friction, missing federation features, broken MFA posture, or a sustained mismatch between Keycloak roles and the platform identity taxonomy.
> Alternative Product: Authentik or Zitadel.

Two 2026-08-26/27 incidents (`docs/postmortems/2026-08-26-0mcp-nginx-edge-network-outage.md`) demonstrated exactly this friction: Keycloak was found running from the undocumented, "temporary migration recovery" host (`docker-runtime` instead of the ADR-0056-documented `runtime-control`), with five independent stale-address bugs (nginx `proxy_pass`, `pg_hba.conf`, `oauth2-proxy`'s JWKS URL, its own `KC_HOSTNAME`, and a Liquibase migration-checksum mismatch from an unpinned image tag) accumulating silently before anyone noticed the login flow was broken. Recovery required deep, one-off forensic work rather than following a governed runbook, and none of it was caught by monitoring because the health-probe catalog entries were themselves stale placeholders.

The operator has decided to replace Keycloak with Authentik rather than continue investing in Keycloak's recovery, for reasons independent of the incident itself:

- **Agentic / API-first**: Authentik exposes a full REST API, an official Terraform provider (`goauthentik/authentik`), and git-friendly YAML "Blueprints" for declaratively defining flows, providers, and applications — a better fit for this repo's "everything as code" governance than Keycloak's realm-export JSON.
- **OpenBao integration**: no special native integration is required or exists on either side — both products take secrets via environment injection, so Authentik slots into the existing generic `openbao_compose_env` sidecar mechanism (ADR 0077) exactly like every other service in this fleet.
- **Fleet fit**: standard deployment is `authentik-server` + `authentik-worker` + PostgreSQL + Redis, matching the compose-per-service pattern already used everywhere on this fleet.

### Current Keycloak footprint (audited 2026-08-27)

The live `0mcp` realm has 12 users (1 real human operator `florin.badita`, 1 real automation account `outline.automation`, break-glass/bootstrap admins, and `service-account-*` technical users for client-credentials clients) and 25 registered OIDC clients (6 Keycloak built-ins + 19 application clients). Cross-referencing against actually-deployed services:

- **Real, currently in use**: `ops-portal-oauth`, `grafana-oauth`, `outline`, `glitchtip`, `lv3-plane-oidc`, `harbor`, `gitea-oauth` (confirmed live: `/opt/gitea` + `/opt/gitea-runner` are real, deployed), `api-gateway` (confirmed live: `/opt/api-gateway` on `runtime-control`, `api.example.org` responds), `serverclaw-runtime` (documented in `docs/runbooks/configure-keycloak.md` as a delivered, cross-repo delegated-auth surface consumed by the ServerClaw repo's own CI).
- **Ghost, safe to drop**: `dify`, `directus`, `paperless`, `superset`, `grist`, `langfuse` (all confirmed via the `docker-runtime` service watchdog as never-deployed — `compose directory does not exist`), `nomad` (no footprint anywhere on the fleet; this fleet doesn't run Nomad).
- **Ambiguous, needs owner confirmation before migration**: `0mpc-agent-hub` / `0mcp-agent-hub` (two renamed registrations, zero live footprint found — may be an intended-but-unrealized agent integration point, not necessarily dead), `serverclaw` (distinct from the documented `serverclaw-runtime`; unclear if this is a second real surface or leftover).

This scopes the real migration effort at Phase 2 (below) to roughly 9 real clients plus 2 ambiguous ones to confirm, not all 19.

## Decision

We will replace Keycloak with Authentik as the shared SSO and identity-broker layer for internal operator-facing and approved agent-facing applications, following the migration path ADR 0056's own exit plan already prescribed: stand up the replacement in parallel, mirror critical clients and group mappings, cut applications over one by one behind the shared edge, verify operator login and service-client flows, then retire Keycloak once all governed apps authenticate cleanly.

Initial expectations (carried over unchanged from ADR 0056, since the identity taxonomy itself isn't changing, only the broker):

1. Human operators authenticate through named accounts with MFA-capable policies.
2. Applications prefer OIDC or SAML integration instead of local password databases.
3. Service and agent clients use scoped confidential clients or equivalent brokered identities where appropriate.
4. Role and group design follows the platform identity taxonomy rather than app-local ad hoc roles.

Initial integration targets (the 9 confirmed-real clients from the audit above): `ops-portal-oauth`, `grafana-oauth`, `outline`, `glitchtip`, `lv3-plane-oidc`, `harbor`, `gitea-oauth`, `api-gateway`, `serverclaw-runtime`.

## Replaceability Scorecard

- Capability Definition: `identity_provider` as defined in `config/capability-contract-catalog.json` (required outcomes, service guarantees, and migration expectations already formally specified there, independent of which product satisfies them).
- Contract Fit: strong — Authentik satisfies the same OIDC discovery/authorization/token/JWKS contract the `identity_provider` capability requires, plus native SAML support and group-aware login.
- Data Export / Import: Authentik has no automated Keycloak import tool (confirmed via research); migration is a manual, per-client re-creation via Authentik's REST API or a checked-in Blueprint YAML file, using the real-client audit above as the worklist. User passwords cannot be migrated as hashes across products — real users get a first-login password reset, not a silent carryover.
- Migration Complexity: medium-high — same class of risk ADR 0056 flagged (every dependent application, callback URL, and `oauth2-proxy` config must cut over without locking out the one real human operator), narrowed in practice by the audit above to 9 real clients instead of 25.
- Proprietary Surface Area: low — Authentik's Blueprint YAML format is explicitly designed to be checked into version control, a better fit for this repo's governance model than Keycloak's realm-export JSON.
- Approved Exceptions: Authentik-native Blueprint/flow semantics are accepted while the canonical operator, service, and agent identity taxonomy remains repo-governed, unchanged from ADR 0056's own exception.
- Fallback / Downgrade: per-application local admin accounts plus `step-ca`-protected break-glass access, unchanged from ADR 0056.
- Observability / Audit Continuity: Authentik exposes login/audit events via its own API and Prometheus metrics endpoint; the same Uptime Kuma + Prometheus liveness/readiness pattern already used for every other service in this fleet applies unchanged.

## Vendor Exit Plan

- Reevaluation Triggers: the same class of triggers as ADR 0056 (unacceptable upgrade/recovery friction, missing federation features, broken MFA posture, taxonomy mismatch) — if history repeats, don't re-litigate this decision from scratch.
- Portable Artifacts: Authentik Blueprint YAML files (checked into this repo, unlike Keycloak's `.local/`-only realm exports), OIDC client inventory, group and role mappings, `oauth2-proxy` configuration, runbooks.
- Migration Path: same shape as this ADR's own — stand up the replacement in parallel, mirror clients, cut over one by one, retire the old broker last.
- Alternative Product: Zitadel (the other option ADR 0056 already named) or a hosted IdP, if a future reevaluation trigger fires.
- Owner: platform identity.
- Review Cadence: quarterly.

## Consequences

- Identity broker configuration becomes git-native (Blueprint YAML) instead of living only in a runtime realm export.
- The `identity_provider` capability contract now selects Authentik and the active catalog, health, SLO, and dependency records name it as the identity service.
- Real users and confidential clients require a coordinated, one-by-one cutover; this is not a same-day flip.
- Ghost OIDC client registrations (`dify`, `directus`, `paperless`, `superset`, `grist`, `langfuse`, `nomad`) do not need to be recreated in Authentik at all — they were never backing a real integration.

## Boundaries

- Authentik does not replace OpenBao for secrets or dynamic credentials, unchanged from ADR 0056's own boundary.
- SSH certificate and internal TLS issuance still belong to `step-ca`, unchanged.
- Local break-glass accounts remain necessary where service recovery would otherwise depend on the failed identity provider itself, unchanged.

## Implementation Notes

- Phases 1–4 are live as of 2026-08-31. Authentik runs on the designated identity runtime, reconciles the declared OAuth clients and identities, and is the issuer used by active OIDC consumers and the shared edge proxy.
- Live verification covered Authentik readiness and signing material, provider reconciliation, an operator authorization-code flow, protected-edge redirects, API bearer-token acceptance and rejection behavior, Grafana OAuth redirect, and GlitchTip OIDC plus event-ingestion checks.
- The retired Keycloak compose stacks were archived on each former runtime host and stopped only after those checks passed. Runtime volumes and archive material remain retained for the documented rollback window; no active Keycloak container, edge route, health probe, or dependency contract remains.
