# ADR 0310: First-Run Activation Checklists And Progressive Capability Reveal

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-31

## Context

ADR 0108 gives the platform a governed way to provision access. ADR 0242 gives
the platform a way to show contextual tours inside pages. Those are both useful,
but a gap remains between "the account exists" and "the human can now succeed
inside the platform without guessing."

New operators still need a clear first-run flow that answers:

- what do I need to finish before I can safely operate?
- what should I open first?
- which actions are safe for a new user and which are advanced?
- how do I know I am done with onboarding?

## Decision

We will add a cross-surface **activation checklist** and use **progressive
capability reveal** for advanced or destructive actions.

### Activation stages

The first-run checklist is organized into these stages:

1. **Identity and access**: confirm login, MFA, and required access paths
2. **Orientation**: understand the workbench lanes, home surface, and help path
3. **Safe first task**: complete a read-only or reversible starter action
4. **Collaboration and alerts**: understand notifications and escalation paths
5. **Advanced capability unlock**: reveal higher-risk actions only after the
   earlier stages are complete or intentionally skipped by an authorised user

### Checklist behavior

- every checklist item must link to its authoritative runbook, tour, or page
- checklist progress must be resumable after logout or interruption
- completion means "ready for routine use", not "knows every platform feature"

### Capability reveal rule

- advanced change paths may remain hidden or visibly disabled until the user
  completes required orientation steps or the role policy explicitly permits
  bypass
- when an action is disabled, the UI must explain which prerequisite is missing
  and how to complete it

## Consequences

**Positive**

- onboarding becomes measurable and goal-oriented instead of "read a lot and
  hope it sticks"
- new users get safer first-run behavior with clearer guardrails
- tours, docs, and launcher favorites can all plug into one onboarding story

**Negative / Trade-offs**

- checklist content becomes product surface area that must stay current as the
  platform evolves
- hiding or deferring capabilities can frustrate experienced users if the rules
  are overly rigid

## Boundaries

- This ADR does not replace role-based authorization.
- This ADR does not replace full training or detailed runbooks.
- This ADR governs activation flow, not account provisioning mechanics.

## Related ADRs

- ADR 0108: Operator onboarding and offboarding workflow
- ADR 0122: Browser-first operator access management
- ADR 0242: Guided human onboarding via Shepherd tours
- ADR 0299: Ntfy as the self-hosted push notification channel
- ADR 0308: Journey-aware entry routing and saved home selection

## References

- [Operator Onboarding](../runbooks/operator-onboarding.md)
- [Guided Human Onboarding Via Shepherd Tours](0242-guided-human-onboarding-via-shepherd-tours.md)
