# ADR 0248: Session And Logout Authority Across Keycloak, Oauth2-Proxy, And App Surfaces

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

For a large estate of protected browser applications, login correctness is only
half the problem. Logout correctness matters just as much:

- stale edge cookies can leave a user unexpectedly authenticated
- application-local sessions can survive after the identity session ends
- logout paths can behave differently between production, staging, and preview

## Decision

We will make **Keycloak** the session authority for protected browser surfaces
and govern logout semantics across Keycloak, `oauth2-proxy`, and application
sessions as one platform contract.

### Required logout behavior

- operator-initiated logout must invalidate the active browser session
- a user must not remain effectively logged in because only one layer cleared
  state
- protected surfaces must prove the post-logout unauthenticated redirect or
  challenge path

### Contract rule

- app-local sessions may exist, but they must respect the platform session
  authority
- if a product cannot participate fully in platform logout, that gap must be
  declared and covered by shorter session TTLs or explicit warnings

## Consequences

**Positive**

- login and logout become platform properties instead of per-product surprises
- session bugs are easier to reason about across many protected services
- operators get more predictable security behavior when moving among surfaces

**Negative / Trade-offs**

- some third-party products may not align perfectly with the platform session
  model
- logout failures become a first-class operational issue instead of a cosmetic
  annoyance

## Boundaries

- This ADR governs browser sessions, not API bearer-token revocation.
- This ADR does not require one universal cookie implementation inside every
  product; it requires coherent authority and verification.

## Related ADRs

- ADR 0056: Keycloak for operator and agent SSO
- ADR 0133: Portal authentication by default
- ADR 0247: Authenticated browser journey verification via Playwright

## References

- <https://www.keycloak.org/docs/latest/server_admin/#_user-sessions>
