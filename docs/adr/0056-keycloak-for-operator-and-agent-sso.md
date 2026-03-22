# ADR 0056: Keycloak For Operator And Agent SSO

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.65.0
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
