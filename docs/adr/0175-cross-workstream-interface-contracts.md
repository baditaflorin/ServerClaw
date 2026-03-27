# ADR 0175: Cross-Workstream Interface Contracts

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.176.1
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-27
- Date: 2026-03-26

## Context

Parallel workstreams are most fragile at their boundaries. One branch changes a role variable name, another branch consumes the old variable. One branch restructures generated service facts, another branch reads the previous shape. Even when file ownership is clear, teams still block each other if shared interfaces are implicit.

The repository already contains many natural interfaces:

- role inputs and outputs
- generated config schemas
- inventory variables
- service capability catalog entries
- workflow catalog fields
- receipt formats

These boundaries need contract files and compatibility checks so multiple agents can work at once without waiting for each other to inspect implementation details.

## Decision

We will define **explicit interface contracts** for shared producer-consumer boundaries touched by more than one workstream, starting with the workstream registry and the live-apply converge workflow handoff.

### Contract requirements

Every shared interface must declare:

- `contract_id`
- owner workstream or owning component
- version
- input schema
- output schema
- compatibility policy
- validator or fixture-based tests

### Storage

Contracts live under a dedicated path such as:

```text
config/contracts/
```

Example:

```yaml
contract_id: service-capability-catalog-v1
owner: adr-0075-service-catalog
version: 1.0.0
compatibility: backward_compatible_minor
producer_paths:
  - config/service-capability-catalog.json
consumer_paths:
  - scripts/generate_platform_vars.py
  - scripts/validate_service_catalog.py
required_fields:
  - service_id
  - vm_hostname
  - dependencies
```

The initial implemented set is:

- `workstream-registry-v1`
- `converge-workflow-live-apply-v1`

### Change policy

- breaking contract changes require a new contract version
- consumers may pin accepted versions
- CI must run producer and consumer compatibility tests before merge

## Consequences

**Positive**

- Workstreams can evolve independently behind stable contracts.
- Review comments shift from "I think this might break something" to concrete compatibility failures.
- Shared surfaces become safer to classify as `shared_contract` under ADR 0173.

**Negative / Trade-offs**

- Contract authoring adds upfront work.
- Some existing interfaces are poorly defined and will need cleanup before they can be formalized.

## Boundaries

- Contracts describe interfaces, not execution order; sequencing still belongs to dependency and apply planning ADRs.
- Not every internal helper needs a contract; only shared boundaries do.
- Additional shared boundaries can add new contract files under `config/contracts/` without changing the existing validator entrypoints.

## Related ADRs

- ADR 0063: Centralised vars and computed facts library
- ADR 0075: Service capability catalog
- ADR 0173: Workstream surface ownership manifest
- ADR 0176: Inventory sharding and host-scoped ansible execution
