# ADR 0259: n8n As The External App Connector Fabric For ServerClaw

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.79
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

The first live platform verification for this ADR became true on 2026-03-29 at
platform version `0.130.50`, which is why the ADR records that first verified
platform version instead of the later integrated replay.

That branch-local live apply was followed by an exact-main replay on 2026-03-29
from source commit `c54fe1c579551248792f064e4e281d00aebf6bd0` on top of latest
`origin/main` commit `4a1f518ab7b0f7e5a997110f55c683a6700c1667`
(`VERSION` `0.177.79`, integrated platform baseline `0.130.53`). The exact-main
proof re-ran `make converge-n8n`, confirmed the protected editor redirect,
confirmed unauthenticated webhook ingress still reaches n8n without the browser
auth redirect, verified guest-local readiness and owner-login on
`docker-runtime-lv3`, and re-confirmed the repo-managed runtime adjustments that
pin topology lookups to `proxmox_florin`, run `n8n` in host-network mode, and
avoid unrelated shared static-site sync prerequisites in fresh worktrees.

The integrated mainline replay advanced the platform baseline to `0.130.54` and
recorded a canonical mainline receipt for the merged truth.

## References

- <https://docs.n8n.io/>
