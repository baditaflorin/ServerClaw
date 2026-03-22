# ADR 0032: Shared Guest Observability Framework

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The repository now has multiple guest-observability paths:

- `roles/nginx_observability`
- `roles/docker_build_observability`
- monitoring dashboard templates that understand service-specific panels

These paths follow similar patterns:

- install Telegraf and any prerequisite repositories
- copy a guest-writer token
- render one or more Telegraf fragments
- restart and verify services
- extend Grafana with service-specific views

That duplication is manageable now, but it will get worse as PostgreSQL, PBS, or future services gain guest-local telemetry.

## Decision

We will introduce a shared guest-observability framework and keep service-specific details as thin extensions.

The framework will own:

1. Common Telegraf installation and repository setup.
2. Common guest-writer token handling.
3. Common directory layout and service verification.
4. A consistent pattern for service roles to add only their input plugins, tags, and verification logic.
5. Shared Grafana panel macros where different services need the same query or panel shape.

## Consequences

- New service telemetry becomes cheaper to add because the plumbing is reused.
- Existing service observability roles become smaller and easier to review.
- Token and Telegraf behavior stop drifting between guests.
- A migration step is required to pull common behavior out of the current service-specific roles without breaking live monitoring.

