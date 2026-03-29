# ADR 0295: Shared Artifact Cache Plane For Container And Package Dependencies

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.73
- Implemented In Platform Version: 0.130.59
- Date: 2026-03-29

## Context

ADR 0089 established host-local build caches on `docker-build-lv3`, and ADR
0274 codified cache-first base-image mirrors for governed repo deployments, but
the current platform still pulls many routine images directly from external
registries at the moment they are needed.

The current image inventory already spans several upstream registries:

- `docker.io` for most runtime services
- `ghcr.io` for Homepage
- `artifacts.plane.so` for Plane
- `docker.n8n.io` for n8n
- `registry.lv3.org` for internal check-runner and platform-built images

That means a simple converge, validation run, or recovery action can still fail
because of upstream throttling, transient network errors, or a slow cold pull
against an image the platform uses repeatedly.

The same underlying problem will recur for package ecosystems that behave like
artifact downloads rather than mutable application state:

- container images
- npm package tarballs
- PyPI wheels and source distributions
- future language or toolchain download surfaces

The platform needs one governed pattern for these reusable dependencies instead
of solving each cache as a disconnected local workaround.

## Decision

We will treat reusable dependency downloads as a **shared artifact cache plane**
with one internal operational model and ecosystem-specific adapters.

### First-class cache plane rules

- cache surfaces exist to improve availability, latency, and repeatability for
  expected dependency pulls
- cache surfaces are internal-only and are not published through the public
  edge
- caches are accelerators and availability buffers, not sources of truth
- upstream digest pinning, vulnerability receipts, and promotion policy remain
  authoritative even when a cache serves the bytes
- cache warming targets are derived from repo-managed manifests and catalogs,
  not from ad hoc operator memory

### First implementation target

The first implementation target is **container image caching** because it is
already a repeated operational pain point and the platform has explicit image
truth in `config/image-catalog.json`, `config/check-runner-manifest.json`, and
`config/validation-gate.json`.

The container-image cache plane will use:

- pull-through registry mirrors for the upstream registries the platform uses
  repeatedly
- an internal warm set derived from repo-managed image references
- consumer integration on the build path first, then broader runtime adoption

### Future ecosystem expansion

When npm, PyPI, or similar ecosystems are added, they must follow the same
governing model:

- one declared cache surface per upstream or ecosystem boundary
- one repo-managed seed or retention policy
- one operational runbook
- no public exposure by default

## Consequences

**Positive**

- routine pulls stop depending on a perfect upstream response every time
- repeated repo-managed operations become faster and less fragile
- future npm and PyPI caching work can extend one shared pattern instead of
  inventing a new one
- dependency policy stays compatible with ADR 0068 rather than bypassing it

**Negative / Trade-offs**

- cache storage, retention, and warming become another managed operational
  surface
- stale or partial cache state can create confusing failures if cache warming is
  not governed
- pull-through mirrors do not remove the need for upstream governance, digest
  pinning, or vulnerability review

## Boundaries

- This ADR governs reusable dependency caching for container and package
  artifacts.
- It does not replace the internal source registry, image promotion policy, or
  repo-managed image digests.
- It does not require every runtime host to switch to mirrored endpoints in the
  first phase.

## Related ADRs

- ADR 0068: Container image policy and supply chain integrity
- ADR 0082: Remote build execution gateway
- ADR 0083: Docker-based check runner on build server
- ADR 0089: Build artifact cache and layer registry
- ADR 0274: Governed base-image mirrors and warm caches for repo deployments
