# ADR 0046: Identity Classes For Humans, Services, And Agents

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.45.0
- Implemented In Platform Version: 0.26.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The platform already distinguishes `ops`, `root`, `ops@pam`, and `lv3-automation@pve`, but future automation will add more identities quickly.

Without a durable identity taxonomy, the platform will drift toward:

- shared credentials
- unclear ownership
- broad privileges that are hard to rotate
- agents impersonating humans because there is no better category

## Decision

All platform identities must belong to one of four classes.

### 1. Human Operator Identities

- named people only
- used for interactive administration and review
- must be attributable to one person

### 2. Service Identities

- used by long-running applications and infrastructure components
- not used for human login
- scoped to one service or one stack

### 3. Agent Identities

- used by automation agents, workflow runners, or controller-side tooling
- must be narrower than break-glass and must not reuse human credentials
- must carry metadata that identifies the owning workflow or automation surface

### 4. Break-Glass Identities

- reserved for recovery only
- heavily restricted, documented, and auditable
- not used for normal automation

Every identity must have:

- an owner
- a purpose
- a scope boundary
- a rotation or expiry model
- a documented storage location for its credential material

## Consequences

- The platform gains a shared vocabulary for access review and automation design.
- New apps can be integrated without falling back to generic administrative users.
- Audit and rotation procedures become easier because each credential belongs to a known class.

## Implementation Notes

- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/versions/stack.yaml) now defines the enforced identity taxonomy, the required metadata contract, and the current managed principals for humans, services, agents, and break-glass use.
- [scripts/validate_repository_data_models.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/validate_repository_data_models.py) now validates the taxonomy in the standard `make validate` gate and cross-checks it against the current Proxmox and mail identities already declared elsewhere in canonical state.
- [docs/runbooks/identity-taxonomy-and-managed-principals.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/identity-taxonomy-and-managed-principals.md) documents how operators should classify, review, and extend the inventory.
- The current shared SSH key path between `ops` and `root` is now explicit repository debt instead of hidden coupling, which leaves ADR 0047 as the follow-up to replace it with short-lived credentials.
- Live review from `main` on 2026-03-22 confirmed that `ops`, `ops@pam`, `lv3-automation@pve`, `server@example.com`, and `root` still match their declared human, agent, service, and break-glass classes.
