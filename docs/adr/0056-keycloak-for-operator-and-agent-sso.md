# ADR 0056: Keycloak For Operator And Agent SSO

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.66.0
- Implemented In Platform Version: 0.34.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The platform is adding more operator-facing and agent-facing applications:

- Grafana
- Windmill
- OpenBao
- NetBox
- Portainer
- Mattermost
- future internal APIs and dashboards

Without a shared identity broker, each application will accumulate its own local users, role model, and session policies.

## Decision

We will use Keycloak as the shared SSO and identity-broker layer for internal operator-facing and approved agent-facing applications.

Initial expectations:

1. Human operators authenticate through named accounts with MFA-capable policies.
2. Applications prefer OIDC or SAML integration instead of local password databases.
3. Service and agent clients use scoped confidential clients or equivalent brokered identities where appropriate.
4. Role and group design follows the platform identity taxonomy rather than app-local ad hoc roles.

Initial integration targets:

- Grafana
- Windmill
- NetBox
- Portainer
- Mattermost

## Replaceability Scorecard

- Capability Definition: `operator_identity_broker` as defined by ADR 0046 identity classes, ADR 0047 short-lived credential policy, and the Keycloak operator runbook.
- Contract Fit: strong for shared OIDC and SAML brokering, MFA-capable operator login, and scoped service or agent clients across internal apps.
- Data Export / Import: realm exports, client definitions, group and role mappings, identity-provider settings, and oauth2-proxy integrations can be exported and recreated on another broker.
- Migration Complexity: medium because every dependent application, callback URL, oauth2-proxy config, and operator session policy must be cut over without locking out administrators.
- Proprietary Surface Area: medium because realm, client, and role semantics are Keycloak-shaped even though the repo keeps canonical identities, app ownership, and auth publication intent outside the broker.
- Approved Exceptions: Keycloak-native realm export structure and admin API workflows are accepted while the canonical operator, service, and agent identity taxonomy remains repo-governed.
- Fallback / Downgrade: per-application local admin accounts plus step-ca-protected break-glass access can preserve minimum operator control while a replacement identity broker is brought online.
- Observability / Audit Continuity: login events, admin audit records, oauth2-proxy logs, and app health probes remain the continuity surface through migration.

## Vendor Exit Plan

- Reevaluation Triggers: unacceptable upgrade or recovery friction, missing federation features, broken MFA posture, or a sustained mismatch between Keycloak roles and the platform identity taxonomy.
- Portable Artifacts: realm exports, client inventory, group and role mappings, oauth2-proxy configuration, runbooks, and application OIDC integration manifests.
- Migration Path: stand up the replacement broker in parallel, mirror critical clients and group mappings, cut apps over one by one behind shared edge auth, verify operator login and service-client flows, then retire Keycloak once all governed apps authenticate cleanly.
- Alternative Product: Authentik or Zitadel.
- Owner: platform identity.
- Review Cadence: quarterly.

## Consequences

- Operator access becomes more consistent across the internal control plane.
- Agents gain a governed identity path for UI-adjacent or API-adjacent integrations.
- Session policy, MFA, and group membership stop being reimplemented in every application.
- Keycloak becomes critical identity infrastructure and must be backed up and monitored like other control-plane state.

## Boundaries

- Keycloak does not replace OpenBao for secrets or dynamic credentials.
- SSH certificate and internal TLS issuance still belong to `step-ca`.
- Local break-glass accounts remain necessary where service recovery would otherwise depend on the failed identity provider itself.

## Implementation Notes

- Keycloak now runs on `docker-runtime-lv3` with a managed PostgreSQL backend on `postgres-lv3` and is published through the shared NGINX edge at `https://sso.lv3.org`.
- The initial live realm is `lv3` with the groups `lv3-platform-admins`, `grafana-admins`, `grafana-viewers`, and `approved-agent-clients`.
- The named human operator `florin.badita` is provisioned with a bootstrap password and the required action `CONFIGURE_TOTP`, while the master-realm bootstrap admin remains a break-glass recovery path only.
- The confidential clients `grafana-oauth` and `lv3-agent-hub` are provisioned and their controller-local secrets are mirrored under `.local/keycloak/`; the agent client-credentials flow is verified live.
- Grafana now uses Keycloak Generic OAuth for the public login path while retaining the local admin account as the documented break-glass fallback.
