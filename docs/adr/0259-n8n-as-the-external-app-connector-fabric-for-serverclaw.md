# ADR 0259: n8n As The External App Connector Fabric For ServerClaw

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: 0.130.50
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

An OpenClaw-like product needs practical connectors for:

- email
- calendars
- tasks
- CRM and ticketing systems
- generic webhook-driven SaaS

The current repository already runs n8n, but the platform still lacks one clear
decision that makes it the connector layer for a user-facing assistant product
instead of just another standalone service.

## Decision

We will use **n8n** as the external app connector fabric for ServerClaw.

### Connector rule

- n8n workflows are the default adapter layer for third-party SaaS and personal
  productivity systems
- ServerClaw calls n8n through governed ports, webhooks, queues, or API routes
  rather than embedding vendor-specific workflow logic into the assistant core

### Logic rule

- n8n handles integration plumbing, credential exchange, and vendor-specific
  translation
- core assistant decisions, skill behavior, and long-running session logic stay
  in ServerClaw runtimes such as Temporal and the governed tool layer

## Consequences

**Positive**

- The assistant core stays cleaner because vendor-specific workflow glue moves
  to a mature adapter plane.
- Existing repo investment in n8n becomes directly useful for a user-facing
  assistant product.
- Connector logic can be reviewed, versioned, and replaced separately from the
  main agent runtime.

**Negative / Trade-offs**

- n8n becomes a higher-value runtime because more user-facing behavior depends
  on it.
- Poorly designed n8n flows could still accumulate business logic if the
  boundary is not enforced.

## Boundaries

- n8n is the connector fabric, not the source of truth for user identity,
  authorization, or assistant memory.
- This ADR does not require every current platform integration to move into n8n.
- Thin adapters are preferred; stateful assistant reasoning should not be
  hidden inside low-visibility workflow nodes.

## Related ADRs

- ADR 0206: Ports and adapters for external integrations
- ADR 0258: Temporal as the durable ServerClaw session orchestrator

## Implementation Notes

The live platform implementation was re-verified on 2026-03-29 by replaying
`make converge-n8n` from rebased latest-`origin/main` commit
`07898c3787d68260df5caecfc5d61eb942255bd3`. The branch-local proof covers the
protected editor redirect, unauthenticated webhook ingress, guest-local
readiness and owner-login checks, and the repo-managed runtime adjustments that
pin topology lookups to `proxmox_florin`, run `n8n` in host-network mode, and
avoid unrelated shared static-site sync prerequisites in fresh worktrees.

The main-only integration files still remain pending until merge:
`VERSION`, release sections in `changelog.md`, the top-level `README.md`
integrated status summary, and `versions/stack.yaml`.

## References

- <https://docs.n8n.io/>
