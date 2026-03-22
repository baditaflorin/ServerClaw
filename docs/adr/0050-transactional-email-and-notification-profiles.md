# ADR 0050: Transactional Email And Notification Profiles

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

ADR 0041 establishes the mail platform direction, but the system still needs a policy for how different senders use it.

The platform will need at least these messaging use cases:

- operator alerts
- application transactional email
- agent-generated reports
- health and backup notifications

If every service uses one generic SMTP login and sender identity, audit and abuse handling become weak.

## Decision

We will define distinct notification profiles on top of the mail platform from ADR 0041.

Initial profile set:

1. operator alerts
2. platform transactional mail
3. agent and workflow reports
4. future application-specific senders

Each profile must have:

- a dedicated sender identity
- a documented owner
- a scoped credential
- rate or abuse expectations
- a retention and observability policy

Steady-state rules:

- applications submit mail through the internal mail platform, not directly to arbitrary external SMTP endpoints
- agents do not reuse operator mail credentials
- notification fan-out to webhooks or dashboards should be modeled as part of the same workflow, not as hidden ad hoc shell glue

## Consequences

- Email send becomes a governed control-plane capability instead of a generic side effect.
- Operational noise and business mail can be separated cleanly.
- Credential leaks become easier to contain because each sender profile can be revoked independently.

