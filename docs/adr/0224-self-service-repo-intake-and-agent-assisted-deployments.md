# ADR 0224: Self-Service Repo Intake And Agent-Assisted Deployments

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
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

Observed on 2026-03-28:

- GitHub SSH access from the controller works for that repository.
- The committed remote `HEAD` currently contains only `.gitignore` and
  `index.html`.
- A separate local working tree on the operator Mac contains uncommitted Vite
  application changes, but that branch-local work is not yet the deployable Git
  truth and currently fails `npm run build` because
  `src/domain/catalog.js` is missing.

That means the first production-safe slice must target the committed Git
revision, not a dirty local checkout, while still leaving room for later
compose-based and agent-repaired application flows.

## Decision

We will extend the existing ADR 0194 Coolify deploy path instead of introducing
a second bespoke app-deployment engine.

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
- treat it as a static-site deployment that serves the committed `index.html`
- postpone compose-first and app-refactor deployment until the upstream
  repository actually commits the new runtime shape

## Consequences

**Positive**

- the platform reuses the live Coolify control plane it already governs
- intake UX, deployment policy, and agent execution stay separable
- repeated repo onboarding can scale through catalog entries and contracts
- private-repo handling becomes explicit instead of implicit operator state

**Negative / Trade-offs**

- private repo credentials now need a proper governed bootstrap path
- autodetect and agent-assisted repair increase the amount of policy metadata
- local dirty checkouts can no longer masquerade as deployable truth

## Boundaries

- This ADR does not replace ADR 0194 or remove Coolify from the deployment
  path.
- This ADR does not authorize direct deployment from an operator's uncommitted
  local filesystem.
- This ADR does not make agent repair fully autonomous; it adds a governed lane
  for bounded assistance.

## Related ADRs

- ADR 0156: Agent session workspace isolation
- ADR 0185: Branch-scoped ephemeral preview environments
- ADR 0194: Coolify PaaS deploy from repo
- ADR 0204: Self-correcting automation loops
