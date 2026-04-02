# ADR 0310: First-Run Activation Checklists And Progressive Capability Reveal

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.144
- Implemented In Platform Version: 0.130.91
- Implemented On: 2026-04-02
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

## Implemented Live Replay

- The exact-main replay on 2026-04-02 used source commit
  `4125edb25791a0e025dfc13976fe847282231712`, cut repository version
  `0.177.144`, advanced the platform lineage from `0.130.90` to `0.130.91`,
  converged the interactive `ops_portal` runtime on `docker-runtime-lv3`, and
  recorded the canonical proof in
  `receipts/live-applies/2026-04-02-adr-0310-activation-checklist-mainline-live-apply.json`.
- The refreshed live replay verified the first-run activation checklist,
  progressive capability reveal, and the server-side launcher, runbook, and
  service-action guardrails on `https://ops.lv3.org`, including the guarded
  guest-local journey that keeps advanced paths locked until the required
  activation steps are complete or intentionally overridden by policy.
- The correction loop is intentionally preserved in
  `receipts/live-applies/evidence/`: the first release-manager replay exposed a
  path-contract failure while `workstreams.yaml` still pointed at absolute
  paths, and the first exact-main live-apply rerun then failed closed because
  canonical truth detected a stale `README.md`. After those repairs, the final
  replay completed successfully with recap
  `docker-runtime-lv3 : ok=192 changed=17 unreachable=0 failed=0 skipped=36`.

## Related ADRs

- ADR 0108: Operator onboarding and offboarding workflow
- ADR 0122: Browser-first operator access management
- ADR 0242: Guided human onboarding via Shepherd tours
- ADR 0299: Ntfy as the self-hosted push notification channel
- ADR 0308: Journey-aware entry routing and saved home selection

## References

- [Operator Onboarding](../runbooks/operator-onboarding.md)
- [Guided Human Onboarding Via Shepherd Tours](0242-guided-human-onboarding-via-shepherd-tours.md)
