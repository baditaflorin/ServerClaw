# ADR 0316: Journey Analytics And Onboarding Success Scorecards

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-31

## Context

The repository has strong operational telemetry:

- uptime and SLO probes
- structured receipts
- deployment history
- Plausible traffic analytics
- Glitchtip application error tracking

What it still lacks is a coherent answer to a product question: are humans
actually getting through onboarding and routine user flows more successfully as
the workbench matures?

Without journey-level measurement, the platform can ship a great-looking shell
and still fail at:

- time to first useful action
- search-to-answer success
- alert-to-acknowledgement speed
- recovery handoff clarity
- interruption and resume success

## Decision

We will define privacy-preserving **journey analytics** and **onboarding
success scorecards** for first-party human flows.

### Core scorecards

The first scorecards should measure:

- time from first authenticated session to first successful safe action
- onboarding checklist completion rate and median completion time
- search or command-palette to destination-open success
- alert-to-acknowledgement and alert-to-resolution handoff time
- resumable-task completion rate after interruption
- help-drawer open to successful recovery or task completion

### Data-source rule

Journey scorecards should combine:

- first-party product events that describe milestones, not user content
- mutation and workflow outcomes from governed backends
- Plausible aggregates for page-flow and route transitions
- Glitchtip signals for user-visible failures that break the intended journey

### Privacy rule

- never capture secrets, free-form document content, or query payloads in
  journey events
- prefer categorical event names and durations over raw text
- measure enough to improve the user flow, but not enough to become a separate
  surveillance system

## Consequences

**Positive**

- the platform can finally tell whether the cohesive-app effort is working
- onboarding becomes a measurable product capability instead of a qualitative
  impression
- future UX changes can be judged on user-flow outcomes, not only visual polish

**Negative / Trade-offs**

- defining and maintaining good product events adds implementation and review
  overhead
- the platform must stay disciplined so scorecards remain actionable and
  privacy-preserving rather than turning into noisy dashboards

## Boundaries

- This ADR does not replace infrastructure monitoring, SLOs, or error budgets.
- This ADR does not authorize collection of content-level user data.

## Related ADRs

- ADR 0123: Service uptime contracts and monitor-backed health
- ADR 0281: Glitchtip as the Sentry-compatible application error tracker
- ADR 0283: Plausible Analytics as the privacy-first web traffic analytics layer
- ADR 0305: k6 for continuous load testing and SLO error budget validation
- ADR 0310: First-run activation checklists and progressive capability reveal

## References

- [Plausible Analytics As The Privacy-First Web Traffic Analytics Layer](0283-plausible-analytics-as-the-privacy-first-web-traffic-analytics-layer.md)
- [Glitchtip As The Sentry-Compatible Application Error Tracker](0281-glitchtip-as-the-sentry-compatible-application-error-tracker.md)
