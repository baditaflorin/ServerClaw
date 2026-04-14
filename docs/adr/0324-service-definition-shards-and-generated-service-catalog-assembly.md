# ADR 0324: Service Definition Shards And Generated Service Catalog Assembly

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.139
- Implemented In Platform Version: 0.130.98
- Implemented On: 2026-04-04
- Date: 2026-04-01
- Tags: services, catalogs, generation, sharding, repo-structure

## Context

The repository now carries enough services that service-shaped facts are repeated
across a small set of increasingly large aggregate files:

- `versions/stack.yaml`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/service-completeness.json`
- `config/dependency-graph.json`
- `config/service-redundancy-catalog.json`
- `config/data-catalog.json`
- `config/slo-catalog.json`

That model worked while the service set was small, but it scales poorly now:

- adding one service requires editing several large files by hand
- multiple workstreams collide on the same catalog surfaces even when they own different services
- service-local reasoning is buried inside platform-wide aggregate documents
- generated summaries such as the README and docs portal must consume monoliths instead of stable per-service inputs

The repository already uses assembly patterns elsewhere. ADR 0174 protects
integration-only truth, and ADR 0038 generates selected status documents from
canonical state. We need the same pattern for service metadata itself.

## Decision

We will move service-shaped repository truth toward **per-service source
bundles** with generated aggregate catalogs.

### Source model

Each managed service will get its own source directory under a dedicated
service-catalog root, for example:

```text
catalog/services/<service-id>/
  service.yaml
  exposure.yaml          # optional
  health.yaml            # optional
  data.yaml              # optional
```

`service.yaml` is the only required file. Optional fragments are allowed when a
service has enough detail to justify splitting further.

### Required service contract

Each service bundle must declare enough information for generators to assemble
the current aggregate views:

- service identity and human title
- deployment placement and runtime lane
- URLs, ports, and exposure tier
- dependencies and upstream/downstream relationships
- health probes and SLO references
- data classes, backup relevance, and redundancy expectations

### Generated outputs

The aggregate surfaces remain useful, but they become **assembled views** rather
than hand-edited sources. Initial targets are:

- the service inventory block in `versions/stack.yaml`
- service-shaped sections of the `config/*catalog*` and `config/*completeness*` files
- service summary surfaces consumed by generated docs and portal tooling

### Validation rule

Generators and validators must enforce:

- one unique service id per bundle
- deterministic output ordering
- schema validation for every bundle fragment
- rejection of hand edits to generated aggregate sections

## Consequences

**Positive**

- service ownership becomes naturally local and easier to review
- parallel service work touches smaller, service-scoped files
- generated status surfaces can assemble from stable building blocks
- adding or retiring a service becomes a directory-level change instead of a
  monolith-edit scavenger hunt

**Negative / Trade-offs**

- the service assembler becomes a critical repo tool
- some cross-service fields will need explicit modeling instead of ad hoc prose
- the first migration will temporarily duplicate information while callers move

## Boundaries

- This ADR governs repository metadata shape, not runtime deployment order.
- This ADR does not replace service-specific runtime config under `config/<service>/`.
- Existing aggregate files may remain as compatibility outputs until callers are
  migrated.

## Related ADRs

- ADR 0038: Generated status documents from canonical state
- ADR 0096: SLO definitions and error budget tracking
- ADR 0104: Service dependency graph
- ADR 0132: Self-describing platform manifest
- ADR 0174: Integration-only canonical truth assembly
