# ADR 0274: Governed Base Image Mirrors And Warm Caches For Repo Deployments

- Status: Accepted
- Implementation Status: Partial
- Implemented In Repo Version: 0.177.31
- Implemented In Platform Version: 0.130.35
- Date: 2026-03-29

## Context

The first private-repo Docker Compose deployments through the ADR 0194 and ADR
0224 Coolify lane showed a repeatable reliability gap:

- anonymous or direct upstream image fetches can fail even when the app itself
  is healthy
- simple base-image resolution failures are wasting full deployment attempts
- the current retry logic helps, but it still reacts after a failure instead of
  preventing it

That is the wrong failure mode for a governed intake lane that is expected to
process many repositories per week. Expected base images should not depend on
best-effort live pulls from public registries during every deployment.

## Decision

We will add a **cache-first base-image policy** for governed repo deployments.

### Required model

Every approved deployment profile must declare the base images it expects to
use, grouped by concern such as:

- language build images
- runtime base images
- common infrastructure images
- stateful service images used by approved compose profiles

### Resolution order

For expected images, the platform will resolve in this order:

1. platform-managed cache or pull-through mirror
2. approved public mirror such as `mirror.gcr.io` when available
3. origin registry only during controlled cache fill or exception handling

Routine deployments should not rely on anonymous Docker Hub resolution for
images that are already in the approved catalog.

### Warm-cache behavior

The platform will maintain warm copies of expected images on the build and
deployment lanes that need them, starting with `coolify-lv3` and any future
remote build workers.

The cache workflow must:

- prefetch declared images on a schedule
- refresh digests on a governed cadence
- record which images were warmed and when
- fail loudly when a required image falls outside policy or freshness bounds

### First implementation slice

The first live slice of this ADR now exists on `coolify-lv3`:

- the governed Docker runtime renders explicit public resolvers for BuildKit
  and container pulls
- the governed Docker runtime pins `https://mirror.gcr.io` as the approved
  Docker Hub mirror for expected public images

Scheduled image warming, freshness receipts, and deployment-profile image
bundles are still pending follow-up work.

### Operator contract

Repo intake and deployment catalogs must reference approved base-image sets
instead of relying on hidden per-repo assumptions.

That means:

- deployment profiles may declare required image bundles
- operators can see which bundle a repo depends on
- cache misses become explicit operational drift, not silent runtime luck

## Consequences

**Positive**

- routine repo deployments become less sensitive to transient registry failures
- expected base images can be warmed before a user-triggered deployment starts
- the platform gains one reusable control instead of one-off per-repo fixes
- deployment receipts can explain whether failures were app logic or supply
  path problems

**Negative / Trade-offs**

- the platform must own image freshness, eviction, and cache storage policy
- approved image bundles become another governed catalog to maintain
- some repos will need exceptions until their Dockerfiles are normalized to the
  approved image catalog

## Boundaries

- This ADR governs expected base images for governed repo deployments.
- It does not replace repository-level Dockerfile hardening when an app needs
  retries or build-specific fixes.
- It does not require every image in every repo to be mirrored immediately; the
  first slice is the approved high-frequency image set.

## Related ADRs

- ADR 0082: Remote build execution gateway
- ADR 0090: Unified platform CLI
- ADR 0093: Interactive ops portal
- ADR 0194: Coolify PaaS deploy from repo
- ADR 0224: Self-service repo intake and agent-assisted deployments
