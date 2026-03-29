# ADR 0224: Server-Resident Operations As The Default Control Model

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.52
- Implemented In Platform Version: 0.130.42
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

The repository is increasingly well-structured, but a large share of actual
platform operation still depends on an interactive authoring client:

- a Codex chat session or local terminal drives the next converge
- a controller-side checkout is treated as the working control plane
- some execution paths still assume a human or agent is present to push the
  platform forward step by step

That is useful for design and implementation work, but it is not a
production-ready operating model. A production platform needs the server-side
control plane to keep running even when no Codex session is open and no laptop
is actively steering it.

## Decision

We will make **server-resident operations** the default control model.

### Responsibility split

- the repository remains the source of truth for design, policy, and desired
  state
- Gitea becomes the server-resident source of merged refs, release bundles, and
  CI evidence
- server-side runners and controllers perform reconciliation, scheduling,
  policy checks, secret retrieval, and bounded command execution
- Codex, Claude, and local terminals become authoring and break-glass clients,
  not the normal runtime for platform control

### Required production properties

The production control model must provide:

- a server-side reconcile loop
- a server-side workflow and approval surface
- local policy evaluation
- local secret delivery
- local execution supervision and audit
- local validation and release preparation
- durable recovery inputs that can be consumed without a live chat session

The follow-on ADRs in this bundle assign those roles to specific mature tools
rather than leaving them as implicit operator behavior.

## Consequences

**Positive**

- The platform becomes less dependent on a workstation or chat session being
  open at the right moment.
- Design-time tools and runtime tools are separated more cleanly.
- Future automation can be reviewed in terms of who authors it versus where it
  actually runs.

**Negative / Trade-offs**

- More server-side control-plane components must be installed, governed, and
  recovered deliberately.
- Interactive shell work will feel less convenient for some workflows because it
  stops being the default path.

## Boundaries

- This ADR does not ban Codex or terminal-driven work. It moves them into the
  authoring and exception layer.
- This ADR does not require all server-side execution to happen on the Proxmox
  host itself. "Server-resident" means within the platform control plane, not
  inside the chat client.

## Related ADRs

- ADR 0044: Windmill for agent and operator workflows
- ADR 0048: Command catalog and approval gates
- ADR 0143: Gitea for self-hosted git and CI
- ADR 0214: Production and staging cells as the unit of high availability
- ADR 0223: Canonical HA topology catalog and reusable automation profiles
