# ADR 0320: Pool-Scoped Deployment Surfaces And Agent Execution Lanes

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.142
- Implemented In Platform Version: 0.130.89
- Implemented On: 2026-04-02
- Date: 2026-04-01

## Context

Splitting `docker-runtime-lv3` into several runtime pools will not improve
parallel work on its own if the repo still deploys everything through one shared
surface.

Today the practical collision domain is often wider than the target service:

- one playbook or compose converge may still touch several unrelated services
- one secret materialization path may force broad restarts
- one execution lane still maps to the whole runtime VM instead of the smaller
  service cluster we actually want to change

If we want multiple agents to work in parallel without blocking one another,
the repository needs a deployment boundary that matches the new runtime-pool
boundary.

## Decision

Every runtime pool must have its own **deployment surface** and its own
**execution lane**.

The first implementation should compose battle-tested API-first tools instead
of inventing new repo-local runtime APIs.

### Required pool-scoped surfaces

Each runtime pool must define all of the following as separate repo-managed
objects:

- inventory target or host group
- service-specific playbook entry point
- runtime role root
- compose project name or Nomad namespace
- Traefik router, service, and middleware identifiers for the pool
- Dapr application ids and component references when the pool uses Dapr
- secret materialization directory and restart scope
- health probes and rollback bundle
- API contract or schema artifact that can be loaded into Microcks for mock and
  conformance testing
- execution lane id used by the scheduler and conflict registry

### Preferred deployment building blocks

For pool-aware delivery we prefer these existing surfaces:

- `Nomad namespaces` or `job groups` for pool-level scheduling boundaries
- `Traefik` dynamic configuration for per-pool publication, retries, and
  traffic shifts
- `Dapr` sidecars and APIs for service invocation, pub/sub, bindings, secrets,
  and workflow hooks where those patterns are needed
- `Microcks` for API mocking, contract validation, and compatibility checks so
  agents do not need custom mock servers or ad hoc test harnesses

### Service-catalog requirements

Every service that lands on a runtime pool must declare:

- `runtime_pool`
- `deployment_surface`
- `restart_domain`
- `api_contract_ref`
- dependency edges that cross into other pools

The default serialisation boundary for service work becomes the runtime pool,
not the whole environment cell.

### Parallel-work rule

- work on different runtime pools may proceed in parallel by default when their
  dependencies are read-only or explicitly declared
- work that touches shared release files or cross-pool topology still belongs
  to the integration step on `main`
- a pool that lacks its own deployment surface is not yet considered safely
  split, even if its services moved to a different VM

## Consequences

**Positive**

- unrelated agents can converge different pools without defaulting to one broad
  restart domain
- rollbacks and probes become smaller and more truthful
- service ownership becomes easier to express in `workstreams.yaml`

**Negative / Trade-offs**

- more deployment surfaces mean more metadata and more validation paths
- shared helpers must stay disciplined or the repo will drift into repeated
  near-duplicate playbooks
- pool-aware delivery will be slower to bootstrap if the contract artifacts
  needed by Traefik, Dapr, or Microcks are missing

## Boundaries

- This ADR governs deploy boundaries and lane ownership, not which product
  runtime each service uses.
- Cross-pool workflows still exist, but they must declare their wider surface
  explicitly instead of piggybacking on one shared runtime converge.

## Related ADRs

- ADR 0079: Playbook decomposition and shared execution model
- ADR 0154: VM-scoped parallel execution lanes
- ADR 0158: Conflict-free configuration merge protocol
- ADR 0173: Workstream surface ownership manifest
- ADR 0175: Cross-workstream interface contracts
- ADR 0176: Inventory sharding and host-scoped Ansible execution
- ADR 0232: Nomad for durable batch and long-running internal jobs
