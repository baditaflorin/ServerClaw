# ADR 0046: Identity Classes For Humans, Services, And Agents

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
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

