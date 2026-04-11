# ADR 0308: Journey-Aware Entry Routing And Saved Home Selection

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.146
- Implemented In Platform Version: 0.130.92
- Implemented On: 2026-04-02
- Date: 2026-03-31

## Context

Not every authenticated user arrives with the same goal:

- a first-day operator needs orientation
- a daily operator wants to resume active work quickly
- a read-only reviewer wants status and documentation, not a mutation-heavy
  dashboard
- a user arriving from an alert needs an attention-first entry point, not a
  generic home page

Today the platform's entry experience is still too memory-driven. Users are
expected to know whether they should start at Homepage, the ops portal, docs,
or a deep-linked product-native screen.

The platform already has role information, protected first-party surfaces, and
planned onboarding tours. What is missing is a declared rule for where the user
should land after sign-in and how they safely get back to the most relevant
home surface.

## Decision

We will use a **journey-aware entry router** and a **saved home** model for
authenticated human users.

### Entry priority order

After authentication, the platform chooses the user's landing surface in this
order:

1. a permitted deep link explicitly requested by the user
2. a resumable onboarding or recovery task that the user has not finished
3. a user-pinned home surface
4. a role-derived default home
5. the neutral start surface when no stronger signal exists

### Default home rules

The first version of the default-home policy is:

| Role | Default home |
| --- | --- |
| `viewer` | Homepage in observe-first mode |
| `operator` | Ops portal in operate-first mode |
| `admin` | Ops portal in govern-and-change mode |

Users may override the default by pinning a preferred home after first-run
orientation is complete.

### First-run rule

- first-run users always land on the onboarding-aware start surface until the
  activation checklist is completed or explicitly skipped
- if the user later returns through an alert or recovery deep link, that urgent
  path wins over the pinned home for that session

## Consequences

**Positive**

- the platform stops treating every authenticated user as though they are at
  the same experience level and working on the same task
- repeat users get a faster return-to-work path
- onboarding and interruption recovery become part of normal entry logic rather
  than bolt-on exceptions

**Negative / Trade-offs**

- entry routing is now a product decision surface that must be governed and
  tested, not just a redirect
- a bad saved-home choice could hide urgent information unless the attention
  routing rules are strong

## Boundaries

- This ADR does not change authorization; a pinned home never bypasses role or
  policy checks.
- This ADR does not replace deep links from alerts, runbooks, or docs when the
  user intentionally opens a specific destination.

## Implemented Live Replay

- The refreshed exact-main replay on 2026-04-02 used source commit
  `36e7636153e2decc324aee8d2c08bdd3d45580ae`, cut repository version
  `0.177.146`, advanced the platform lineage from `0.130.91` to `0.130.92`,
  converged the interactive `ops_portal` runtime on `docker-runtime`, and
  recorded the canonical proof in
  `receipts/live-applies/2026-04-02-adr-0308-journey-entry-routing-mainline-live-apply.json`.
- Guest-local verification confirmed the neutral `Journey-Aware Start Surface`,
  the activation-first routing contract, saved-home pin and clear behavior, the
  shared attention shell, and the oauth2-proxy-gated public
  `https://ops.example.com/entry` edge from the same exact-main line.
- The correction loop is intentionally preserved in
  `receipts/live-applies/evidence/`: replay `r14` failed closed because the
  Docker `nat` `DOCKER` chain stayed missing after guest firewall evaluation,
  and replay `r16` then completed successfully after the bridge-chain recovery
  repair landed on the same branch.

## Related ADRs

- ADR 0108: Operator onboarding and offboarding workflow
- ADR 0133: Portal authentication by default
- ADR 0152: Homepage for unified service dashboard
- ADR 0235: Cross-application launcher and favorites
- ADR 0242: Guided human onboarding via Shepherd tours
- ADR 0307: Platform workbench as the cohesive first-party app frame

## References

- [Operator Onboarding](../runbooks/operator-onboarding.md)
- [Platform Operations Portal](../runbooks/platform-operations-portal.md)
