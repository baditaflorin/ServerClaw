# ADR 0032: Shared Guest Observability Framework

- Status: Accepted
- Implementation Status: Accepted
- Implemented In Repo Version: N/A
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-22
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

## Implementation Notes

- Shared Telegraf and guest-writer token plumbing now lives in [roles/guest_observability](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/guest_observability).
- The framework owns InfluxData repository setup, Telegraf installation, mirrored guest-writer token handling, common directory management, and Telegraf enable plus verification.
- [roles/nginx_observability](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/nginx_observability) and [roles/docker_build_observability](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/docker_build_observability) now keep only service-specific configuration, handlers, and verification.
- The monitoring playbook keeps the same live targets and dashboards while using the shared framework under the role boundary.
