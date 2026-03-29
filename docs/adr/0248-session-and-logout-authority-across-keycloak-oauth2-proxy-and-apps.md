# ADR 0248: Session And Logout Authority Across Keycloak, Oauth2-Proxy, And App Surfaces

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.63
- Implemented In Platform Version: 0.130.45
- Implemented On: 2026-03-29
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

## Live Apply Notes

- Live verification ran from rebased workstream commit
  `7b0bd0230482ef077c17714ad224364badf3171b` by replaying the Keycloak,
  Outline, and public-edge publication paths from the latest `origin/main`
  worktree and then rechecking the shared logout endpoints plus the full
  browser logout journey.
- The shared edge now exposes repo-managed logout surfaces at
  `home.lv3.org/.well-known/lv3/session/logout`,
  `ops.lv3.org/.well-known/lv3/session/proxy-logout`, and
  `ops.lv3.org/.well-known/lv3/session/logged-out`, with NGINX extracting the
  current bearer token from `/oauth2/auth` so Keycloak logout can receive an
  `id_token_hint` where the shared proxy flow supports it.
- Grafana and the shared edge-protected portals now hand logout through that
  governed path without pausing on a Keycloak confirmation page.
- Outline remains the declared gap for perfect RP-initiated logout because it
  cannot supply `id_token_hint` on its app-local logout handoff. The live
  platform now reaches the Keycloak confirmation page consistently, and the
  verifier submits that real confirmation form before proving both
  `home.lv3.org` and `wiki.lv3.org` challenge again after logout.
- The authoritative `make live-apply-service service=outline env=production`
  wrapper was exercised on the workstream branch and correctly stopped at the
  canonical-truth gate because `README.md` is a protected shared integration
  file. The branch therefore records the direct scoped-playbook replay plus the
  passed interface-contract, standby-capacity, redundancy, and immutable-guest
  checks as the safe workstream-branch live-apply evidence.

## References

- <https://www.keycloak.org/docs/latest/server_admin/#_user-sessions>
