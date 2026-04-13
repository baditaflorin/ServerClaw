# WS-0362: Semaphore Keycloak OIDC Draft Notes

This file is retained only as sanitized historical context for the first
branch-local draft of the Semaphore OIDC work.

## Status

- superseded by [ws-0361-live-apply](ws-0361-live-apply.md)
- no secret values or live credential placeholders remain in this document
- the current repo-managed procedure is defined in:
  - [Configure Semaphore](../runbooks/configure-semaphore.md)
  - [Configure Semaphore with Keycloak OIDC](../runbooks/configure-semaphore-keycloak.md)
  - [ADR 0361](../adr/0361-semaphore-keycloak-oidc-integration.md)

## Historical Note

The original draft introduced the Semaphore OIDC environment variables but still
described a manual Keycloak client creation flow and a controller-local secret
path under `.local/semaphore/`.

That procedure is obsolete. The current repo truth is:

- `playbooks/semaphore.yml` reconciles the dedicated `semaphore` Keycloak client
- the mirrored client secret lives at `.local/keycloak/semaphore-client-secret.txt`
- Semaphore consumes that repo-managed secret during converge
- routine sign-in uses Keycloak OIDC, while `ops-semaphore` remains the
  repo-managed break-glass login
