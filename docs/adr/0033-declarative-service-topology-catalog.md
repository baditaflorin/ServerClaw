# ADR 0033: Declarative Service Topology Catalog

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The repository already tracks guests, hostnames, dashboards, edge publication, and service-specific behaviors, but that information is spread across:

- inventory data
- group variables
- Grafana templates
- DNS publication inputs
- edge-publication inputs
- README and versions documentation

That creates repeated facts such as:

- which VM owns a service
- whether a service is public or private
- which hostname belongs to which workload
- whether a workload should appear in dashboards or runbooks

When those facts live in several places, the codebase becomes harder to extend safely.

## Decision

We will introduce one declarative service-topology catalog as the canonical source for workload metadata.

The catalog will describe, at minimum:

1. Service name and owning VM.
2. Private IP and optional public hostname.
3. Exposure model such as private-only, edge-published, or informational-only.
4. Observability expectations such as whether the service gets guest-level dashboards.
5. Inputs that should be rendered into downstream artifacts rather than copied manually into several templates.

## Consequences

- Repeated service facts move into one place.
- Dashboard, DNS, and edge-publication generation become easier to keep consistent.
- Adding a new service becomes more predictable because the same data model drives multiple outputs.
- The first implementation must avoid over-abstracting existing working automation; the catalog should replace repetition, not hide simple behavior behind a framework for its own sake.

