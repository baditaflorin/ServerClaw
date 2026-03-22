# ADR 0045: Control-Plane Communication Lanes

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The system needs a coherent way for humans, services, and agents to communicate with the server through:

- secure commands
- email send
- API access
- internal event callbacks

Today those paths exist in pieces, but the boundaries between them are still implicit.

## Decision

We will standardize on four control-plane communication lanes.

### 1. Command Lane

- purpose: shell-level administration and repair
- transport: SSH only
- network path: Tailscale or private LV3 networks only
- identity: named human or agent identities using approved credentials
- access level: `ops` plus explicit `sudo`, not routine direct `root`

### 2. API Lane

- purpose: service control, automation endpoints, and management APIs
- transport: HTTPS only
- identity: scoped tokens, client certificates, or other approved machine auth
- network path: private-first, with explicit publication rules under the API publication ADR

### 3. Message Lane

- purpose: outbound transactional mail and operator notifications
- transport: authenticated submission to the internal mail platform
- identity: dedicated sender profiles, not shared global SMTP credentials
- network path: private submission to the chosen mail stack

### 4. Event Lane

- purpose: webhooks, callbacks, and asynchronous automation triggers
- transport: signed HTTP requests over private or explicitly published endpoints
- identity: scoped webhook secrets, signatures, or client certificates
- sinks: Windmill, monitoring, or other approved internal consumers

## Consequences

- Secure commands, API access, and mail send stop being vague capabilities and become explicit platform lanes.
- Each lane can be governed with different credentials, rate limits, audit expectations, and publication rules.
- Future apps must declare which lane they use rather than inventing their own one-off control path.

