# ADR 0224: Self-Service Repo Intake And Agent-Assisted Deployments

- Status: Accepted
- Implementation Status: Partial
- Implemented In Repo Version: 0.177.31
- Implemented In Platform Version: 0.130.35
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

ADR 0194 already gives the platform a governed repo-deploy lane through
Coolify. Operators can create or update one application from a Git repository,
bind it to `*.apps.lv3.org`, and trigger deployment through a private API path.

That is a strong base, but it is still operator-first and too thin for the
workflow now being requested:

- an authenticated intake surface where a user submits a repository URL
- a declared output domain and environment selection from a reusable catalog
- optional staging plus production, and later more deployment profiles
- optional LLM wiring for repos that need agent-assisted build, deploy, or
  repair loops
- support for CPU-only repos that should deploy without LLM involvement
- the ability to process this flow repeatedly, at high volume, without relying
  on hidden chat context or manual server drift

The first target repository is private:
`git@github.com:baditaflorin/education_wemeshup.git`.

Observed across 2026-03-28 and 2026-03-29:

- GitHub SSH access from the controller works for that repository.
- The committed upstream `main` has now moved to a Docker Compose-backed
  application with `postgres`, `catalog-api`, and `catalog-web`, and the
  public route `education-wemeshup.apps.lv3.org` is already governed by the
  ADR 0194 Coolify lane.
- The first production pull of the newer app shape surfaced two repeatable
  transient failure classes that do not require a human to redesign the
  deployment:
  - Docker Hub anonymous-token timeouts while resolving base images
  - temporary Alpine package-index failures during runtime image assembly
- The companion application repository merged PR `#2` to remove the external
  Dockerfile frontend pin and PR `#3` to harden Alpine runtime package
  installation retries.

That means the next safe slice is no longer "static page first". It is a
governed repo-deploy path that can pull the latest committed Dockerized app,
survive common transient build-network failures, and expose the same behavior
through a non-chat operator surface later.

## Decision

We will extend the existing ADR 0194 Coolify deploy path instead of introducing
a second bespoke app-deployment engine.

We will also treat the existing workflow and command catalogs as the current
operator-grade contract, and the existing interactive ops portal architecture as
the future browser entry point for this flow. In practice, that means:

- today, the supported non-chat entry points are the catalog-backed
  `make coolify-manage ...` and `python3 scripts/lv3_cli.py deploy-repo ...`
  commands
- tomorrow, the authenticated form or catalog UI should be added on top of the
  ADR 0093 portal and ADR 0092 gateway, calling the same governed contract
- we do not create a second deployment subsystem just because the eventual user
  interface is a browser instead of a terminal

The future self-service flow should be built from five explicit layers:

### 1. Intake contract

Every requested deployment should compile into one repo-managed intake record
with at least:

- repository URL and provider
- branch or revision target
- requested application name
- requested public domain or subdomain
- selected environment profile such as preview, staging, or production
- declared runtime class such as static, dockerfile, docker compose, or
  catalog-driven autodetect
- whether LLM assistance is allowed, required, or prohibited

### 2. Deployment profile catalog

The repository should declare a catalog of approved deployment profiles rather
than letting each request invent its own shape. Profiles should define:

- which environment lanes are allowed
- domain patterns and naming rules
- allowed build strategies
- required secrets or approval gates
- validation probes
- promotion expectations between staging and production

### 3. Private repo credential boundary

Private repository access must be governed and narrow. For server-side clone
access, prefer a GitHub App or per-repository deploy key over a broad personal
access token. The intake flow should reference a credential contract, not raw
secret material embedded in ad hoc commands.

### 4. Agent execution lane

When a repository cannot be deployed by straight catalog rules, the platform
may hand the task to Codex or Claude terminal runtimes through isolated
worktrees and bounded correction loops. Agent execution is for:

- repository inspection
- build and runtime diagnosis
- suggested code fixes
- compose or Docker deployment adaptation

Agent execution is not permission for unsupervised destructive mutation. Any
live repair still needs the declared safety boundary, validation probe, and
receipt path required by ADR 0204.

### 5. Thin-slice bootstrap

The first thin slice for this architecture is intentionally small:

- deploy the committed `education_wemeshup` GitHub repository as a private-repo
  smoke test
- use the existing Coolify repo wrapper, private deploy-key bootstrap, and
  wildcard DNS publication instead of creating an ad hoc path
- harden the deploy wrapper for transient registry and package-mirror failures
  that should be retried automatically

### 6. Current implementation slice

This ADR is now `Partial`, not `Not Implemented`, because the current platform
already has a meaningful first slice in place:

- machine-readable execution surface:
  `config/workflow-catalog.json` and `config/command-catalog.json`
- operator entry points:
  `make coolify-manage ACTION=deploy-repo ...` and
  `python3 scripts/lv3_cli.py deploy-repo ...`
- governed runtime behavior:
  private GitHub deploy-key bootstrap, Docker Compose domain mapping,
  wildcard `*.apps.lv3.org` DNS publication, stale same-app deployment
  cancellation, bounded automatic retry of transient Coolify deployment
  failures, and Docker build-lane hardening through governed Docker daemon
  resolver plus registry-mirror settings on `coolify-lv3`
- still missing:
  the authenticated intake form, environment catalog UI, and policy-driven
  operator workflow at `ops.lv3.org`

## Consequences

**Positive**

- the platform reuses the live Coolify control plane it already governs
- intake UX, deployment policy, and agent execution stay separable
- repeated repo onboarding can scale through catalog entries and contracts
- private-repo handling becomes explicit instead of implicit operator state
- the current non-chat operator path already exists, so the future browser flow
  can wrap a governed contract instead of reverse-engineering shell snippets

**Negative / Trade-offs**

- private repo credentials now need a proper governed bootstrap path
- autodetect and agent-assisted repair increase the amount of policy metadata
- local dirty checkouts can no longer masquerade as deployable truth

## Boundaries

- This ADR does not replace ADR 0194 or remove Coolify from the deployment
  path.
- This ADR does not require Codex chat as the operator surface; terminal and
  future portal flows both use the same governed contract.
- This ADR does not authorize direct deployment from an operator's uncommitted
  local filesystem.
- This ADR does not make agent repair fully autonomous; it adds a governed lane
  for bounded assistance.

## Related ADRs

- ADR 0156: Agent session workspace isolation
- ADR 0035: Workflow catalog and machine-readable execution contracts
- ADR 0048: Command catalog and approval gates
- ADR 0093: Interactive ops portal with live actions
- ADR 0185: Branch-scoped ephemeral preview environments
- ADR 0194: Coolify PaaS deploy from repo
- ADR 0204: Self-correcting automation loops
