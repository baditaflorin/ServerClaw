# ADR 0049: Private-First API Publication Model

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The platform is adding more APIs:

- Proxmox API
- mail platform API
- future secret authority API
- workflow runtime API

Without a publication policy, those APIs will drift toward accidental exposure.

## Decision

Every API must be classified into one of three publication tiers.

### 1. Internal-Only

- reachable only from LV3 private networks or trusted control-plane hosts
- examples: OpenBao, `step-ca`, internal webhook endpoints

### 2. Operator-Only

- reachable from approved operator devices over private access
- examples: Proxmox management, Windmill admin surface

### 3. Public Edge

- intentionally published on a public domain through the edge model
- requires explicit ADR or implementation approval
- examples: public application APIs, not internal admin APIs

Default rule:

- if a new API is not explicitly classified, it is internal-only

## Consequences

- New apps cannot quietly expose administrative ports just because they listen on HTTPS.
- Publication becomes a design decision, not an implementation accident.
- The public edge stays focused on deliberately published services instead of becoming a spillover path for internal control planes.

