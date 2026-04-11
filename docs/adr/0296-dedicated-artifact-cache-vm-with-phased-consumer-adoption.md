# ADR 0296: Dedicated Artifact-Cache VM With Phased Consumer Adoption

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.103
- Implemented In Platform Version: 0.130.69
- Implemented On: 2026-03-30
- Date: 2026-03-29

## Context

The quickest landing point for an artifact cache is the existing
`docker-build` guest because it already owns build-local caches and is the
first consumer that benefits from faster repeated pulls.

That is useful for an initial phase, but it is not an ideal long-term home for
all shared artifact caches:

- build workloads and cache retention compete for the same disk and CPU budget
- package caching is broader than one build host concern
- future npm and PyPI caches should not be coupled to one builder's lifecycle
- a dedicated cache surface is easier to document, monitor, back up, and move
  independently

## Decision

We will adopt artifact caching in **two phases**.

### Phase 1: land on `docker-build`

- the first repo-managed container-image cache runtime may land on
  `docker-build`
- the build path may consume those cache endpoints first
- this phase exists to reduce immediate pull fragility without waiting for a
  new VM integration

### Phase 2: move to a dedicated cache VM

- the steady-state target is a dedicated `artifact-cache` guest
- the planned default slot is VMID `180` with internal address `10.10.10.80/24`
  unless later integration work assigns a different governed slot
- the dedicated cache VM is internal-only and is not published through the
  public NGINX edge
- the VM may host multiple cache adapters over time:
  - container-image pull-through mirrors
  - npm cache surfaces
  - PyPI or wheel caches
  - other governed dependency caches approved by later ADRs

### Consumer adoption rules

- build and CI consumers move first
- runtime hosts adopt the cache plane in later phases once endpoint stability,
  storage policy, and failure handling are proven
- consumer configuration must remain reversible so a cache-plane fault does not
  block recovery to direct upstream access

## Consequences

**Positive**

- cache capacity and build capacity become separately governable
- future npm and PyPI expansion gets a clear runtime home
- the platform can move cache storage or retention policy without redesigning
  the build guest

**Negative / Trade-offs**

- a dedicated VM adds one more managed guest to the platform
- phase 1 and phase 2 documentation must stay aligned to avoid drift
- moving consumers from the build guest to the dedicated VM requires a planned
  migration step

## Boundaries

- This ADR defines topology and rollout order for the artifact cache plane.
- It does not by itself reserve the VM in canonical inventory or
  `versions/stack.yaml`; that happens only when the dedicated guest is accepted
  into merged truth.
- It does not require a live migration before the first build-host-local cache
  implementation is useful.

## Related ADRs

- ADR 0085: OpenTofu-driven Proxmox VM lifecycle
- ADR 0089: Build artifact cache and layer registry
- ADR 0184: Failure-domain labels and placement policy
- ADR 0192: Capacity classes for production and staging guests
- ADR 0295: Shared artifact cache plane for container and package dependencies
