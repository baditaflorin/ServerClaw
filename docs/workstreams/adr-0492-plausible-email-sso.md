# ADR 0492: Scope Plausible SSO to an operator email

- Status: Accepted
- Implementation Status: Live-applied; awaiting final interactive account verification
- Implemented In Repo Version: 0.179.48 source commit 7152a8a
- Implemented In Platform Version: pending release-manager blockers
- Implemented On: 2026-10-05
- Date: 2026-10-05

## Context

`analytics` currently shares the operations OAuth2 Proxy instance, which allows
only members of the `0mcp-platform-admins` group. Authentik successfully
authenticates the named operator account, but that account is not in that group,
so the callback ends at a 403. The same email currently belongs to two active
Authentik accounts. Adding either account to the shared administrator group
would expand access to every hostname using that proxy.

## Decision

Give Plausible a dedicated Authentik authorization-code client and a second
loopback-only oauth2-proxy instance. Enforce access using an exact
`authenticated_emails_file` maintained in the ignored local overlay. Route only
the analytics hostname's OAuth endpoints to this instance. Keep the current
shared proxy, group policy, and remaining protected hostnames unchanged.

The exact email allowlist authorizes the email claim, regardless of which
matching Authentik account completes sign-in. It grants no Authentik group
membership and no access to the operations portal or other protected services.

## Consequences

- Plausible has an independent OIDC client, callback, cookie, and edge proxy.
- Updating this identity's allowed Plausible email requires changing the ignored
  local allowlist and converging the edge.
- Plausible tracking and health endpoints keep their existing public routes.
- Rollback is limited to returning analytics' auth upstream to the shared proxy
  and disabling the dedicated client and service.
