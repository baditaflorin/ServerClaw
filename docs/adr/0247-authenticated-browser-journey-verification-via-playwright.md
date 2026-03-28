# ADR 0247: Authenticated Browser Journey Verification Via Playwright

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

A protected surface is not truly working just because the container is up or
the login page returns `200`.

Human users care about the full browser journey:

- redirect to the identity provider
- successful login
- return to the protected surface
- access to the expected page after authentication
- logout that actually ends the browser session

## Decision

We will use **Playwright** as the default browser-journey verification tool for
auth-protected human-facing surfaces.

### Required journey coverage

- unauthenticated request produces the expected challenge or redirect
- login completes with a governed operator or test identity
- post-login landing page proves the protected app really works
- logout returns the browser to an unauthenticated state

### Stage rules

- production requires smoke coverage for all operator-facing public or
  edge-published browser surfaces
- staging requires the same coverage for surfaces declared ready for operator
  use
- preview environments may use a narrower subset, but only by explicit policy

## Consequences

**Positive**

- browser truth is verified the way humans actually experience the platform
- auth regressions become visible before operators discover them manually
- login and logout become governed assurance dimensions rather than informal
  spot checks

**Negative / Trade-offs**

- browser tests are slower and more brittle than simple HTTP probes
- test identities and session hygiene must be managed carefully

## Boundaries

- This ADR governs human browser journeys, not API token flows.
- Playwright smoke coverage complements but does not replace deeper load or
  synthetic replay testing.

## Related ADRs

- ADR 0133: Portal authentication by default
- ADR 0190: Synthetic transaction replay for capacity and recovery validation
- ADR 0244: Runtime assurance matrix per service and environment

## References

- <https://playwright.dev/docs/auth>
