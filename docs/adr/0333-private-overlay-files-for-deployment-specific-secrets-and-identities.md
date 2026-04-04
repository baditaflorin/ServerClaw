# ADR 0333: Private Overlay Files For Deployment-Specific Secrets And Identities

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: N/A
- Implemented On: 2026-04-04
- Date: 2026-04-02
- Tags: overlays, secrets, identities, local-state, forkability

## Context

Some repo surfaces still need deployment-specific values:

- secrets and mirrored bootstrap credentials
- provider account details
- hostnames, domains, and node identities
- locally generated operator artefacts

Those values are legitimate operational inputs, but they should not live in the
same committed surfaces that make the repo reusable for a new fork.

## Decision

Deployment-specific secrets, identities, and one-off bootstrap artefacts must
live in ignored private overlays or environment-bound inputs, with committed
examples instead of committed real values.

### Storage rule

- `.local/` remains the default ignored home for controller-local artefacts
- environment variables may override local secret paths where automation already supports it
- committed docs may describe overlay expectations, but they should not embed one deployment's real values

### Documentation rule

Public onboarding should reference categories such as "operator SSH key" or
"OIDC client secret" rather than one deployment's concrete filenames whenever a
portable example is sufficient.

## Consequences

**Positive**

- forks can adopt the repo without inheriting someone else's secrets contract
- the repo keeps a clean separation between reusable automation and local state
- public publication no longer conflicts with keeping rich private operator artefacts

**Negative / Trade-offs**

- some existing docs and defaults still need follow-up conversion to example-first overlays
- operators need a slightly clearer bootstrap checklist when standing up a fresh fork

## Boundaries

- This ADR does not ban `.local/`; it formalizes it as private overlay state.
- This ADR does not remove live receipts or canonical runtime truth when those are intentionally committed.

## Related ADRs

- ADR 0034: Controller-local secret manifest and preflight
- ADR 0047: Short-lived credentials and internal mTLS
- ADR 0330: Public GitHub readiness as a first-class repository lifecycle
