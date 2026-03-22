# ADR 0056: Keycloak For Operator And Agent SSO

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
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
