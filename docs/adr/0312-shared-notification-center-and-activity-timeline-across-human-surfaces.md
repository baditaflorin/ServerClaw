# ADR 0312: Shared Notification Center And Activity Timeline Across Human Surfaces

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.146
- Implemented In Platform Version: 0.130.92
- Implemented On: 2026-04-02
- Date: 2026-03-31

## Context

Human-facing platform signals are currently fragmented:

- ntfy is suited to direct pushes and urgent automation escalation
- Mattermost is suited to team-visible discussion
- the changelog portal records deployment history
- the mutation audit log records governed actions
- product-native UIs show their own local alerts and job histories

Those surfaces are all useful, but they do not add up to one coherent in-app
story for "what needs my attention now?" and "what just happened across the
platform?"

## Decision

We will provide a shared **notification center** for actionable items and a
shared **activity timeline** for ambient history across first-party surfaces.

### Two-channel model

- the **notification center** is for items that need a human decision, review,
  acknowledgement, or follow-up
- the **activity timeline** is for passive history such as completed deploys,
  successful recoveries, completed onboarding milestones, and recent actions

### Aggregation sources

The first implementation should aggregate from:

- mutation audit entries
- deployment and live-apply receipts
- onboarding blockers and completion milestones
- ntfy-backed escalation events
- runbook and workflow state changes that matter to a human

### Behavior rules

- severity, status, and acknowledgement language must be consistent across
  first-party surfaces
- every item must deep-link to the owning page, runbook, or receipt
- the notification center must support dismissal or acknowledgement without
  destroying the underlying audit trail

## Consequences

**Positive**

- users gain one predictable place to check attention items
- the platform starts to feel like one app with a shared pulse instead of a set
  of isolated logs
- onboarding and recovery flows can reuse the same attention model as routine
  operations

**Negative / Trade-offs**

- aggregation quality depends on event normalization across many existing
  systems
- if everything is treated as a notification, the center becomes useless; the
  distinction between actionable and historical signals must stay strict

## Boundaries

- This ADR does not replace Mattermost threads, ntfy push delivery, raw logs, or
  the full deployment-history portal.
- This ADR does not require all third-party products to stop showing their own
  native alerts.

## Implemented Live Replay

- The refreshed exact-main replay on 2026-04-02 used source commit
  `36e7636153e2decc324aee8d2c08bdd3d45580ae`, cut repository version
  `0.177.146`, advanced the platform lineage from `0.130.91` to `0.130.92`,
  and recorded the shared-shell proof in
  `receipts/live-applies/2026-04-02-adr-0308-journey-entry-routing-mainline-live-apply.json`
  because ADR 0312 shipped in the same combined portal bundle.
- Guest-local verification confirmed the live `Notification Center` partial and
  the dashboard-level `Attention Center`, `Runbook Launcher`, and
  `Activity Timeline` markers from inside `docker-runtime`.
- The same correction loop evidence preserves the first failed exact-main
  replay and the successful final rerun after the Docker bridge-chain recovery
  repair.

## Related ADRs

- ADR 0066: Mutation audit log
- ADR 0081: Platform changelog and deployment history portal
- ADR 0097: Mattermost for chatops and alerts
- ADR 0161: Real-time agent coordination map
- ADR 0299: Ntfy as the self-hosted push notification channel

## References

- [Deployment History Portal](../runbooks/deployment-history-portal.md)
- `https://changelog.example.com`
