# ADR 0072: Staging And Production Environment Topology

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.75.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
- Date: 2026-03-23

## Context

Later repository surfaces already talk about `production` and `staging` as if they are established platform environments:

- the subdomain catalog already labels hostnames by environment
- the service capability ADR describes per-environment URL overrides
- the operations portal ADR assumes a staging portal instance at `ops.staging.lv3.org`

What is missing is the actual topology decision that says:

- what `production` means on this platform
- what `staging` means on this platform
- whether they are separate estates or shared infrastructure lanes
- which hostname pattern belongs to each environment
- where the canonical environment metadata lives

Without that decision, later automation has to infer environment topology from scattered hints. That is brittle, and it invites accidental reuse of production hostnames or state when a staging surface is introduced.

## Decision

We will model two named environments for this platform: `production` and `staging`.

### Environment model

1. `production` is the live operator and workload environment.
2. `staging` is the pre-production validation lane for selected operator-facing and edge-published services.
3. Both environments currently share the same single-node Proxmox estate and the same NGINX edge VM.
4. A later ADR may introduce dedicated staging capacity, but the initial topology is explicitly **single-node, shared-edge, logically isolated**.

### Naming and publication

1. Production public hostnames use the existing `*.lv3.org` pattern.
2. Staging public hostnames use the `*.staging.lv3.org` pattern.
3. Bare production hostnames must not be reused for staging traffic.
4. Staging publication remains `planned` until the owning service ADR applies it live from `main`.

### Isolation rules

When a service gains a staging surface, staging must not reuse production mutable state. At minimum, staging must use separate:

- DNS names
- secrets and client credentials
- volumes or bind-mounted runtime state
- databases, schemas, or queues when the service persists state

Shared infrastructure is allowed for now:

- Proxmox host
- NGINX edge VM
- operator private access path

Shared mutable application state is not allowed by default.

### Canonical sources

The environment topology is represented through these committed, validated sources:

1. `config/environment-topology.json` for environment-wide topology metadata
2. `config/service-capability-catalog.json` for per-service environment bindings
3. `config/subdomain-catalog.json` for environment-tagged DNS publication intent

Repository validation must reject:

- subdomains that reference an unknown environment
- service environment bindings that do not match the subdomain catalog
- hostnames that do not fit the declared environment domain pattern

## Consequences

- Later ADRs can reference `production` and `staging` without inventing their own topology rules.
- Operators and agents get one explicit answer to "is staging a separate estate or a logical lane on the same host?".
- The operations portal can render an environment view from canonical data instead of hard-coded assumptions.
- The platform still does not have a live staging deployment just because the topology is modeled in the repo; each staging surface needs its own rollout.

## Boundaries

- This ADR defines topology and naming. It does not itself deploy a live staging stack.
- This ADR does not require a second Proxmox node or a second VM estate.
- This ADR does not replace service-specific ADRs for staging rollout details such as databases, volumes, or auth clients.

## Implementation Notes

- Environment-wide metadata now lives in [config/environment-topology.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/environment-topology.json), validated by [scripts/environment_topology.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/environment_topology.py) and [docs/schema/environment-topology.schema.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/schema/environment-topology.schema.json).
- The service capability catalog now requires an explicit `production` binding for every service and supports `staging` bindings where a staged surface is planned.
- The subdomain catalog now includes the missing production `sso.lv3.org` entry plus planned staging hostnames under `*.staging.lv3.org`.
- The operations portal generator now renders an Environment Topology view from the canonical environment, service, and subdomain catalogs.
