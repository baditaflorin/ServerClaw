# ADR 0161: Real-Time Agent Coordination Map

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.151.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Date: 2026-03-25

## Context

The platform already has multiple agent execution paths that can overlap in time:

- the observation loop scans and verifies platform state continuously
- closure-loop actors can plan or apply follow-up work while holding locks
- operators need a shared view of which agent is active, on which target, and whether it is blocked or stale

Before this ADR, that state was fragmented across logs, receipts, and per-process memory. The platform had durable scratch state and handoff primitives, but no shared live map for "what is happening right now". That made it harder to spot overlapping work, stale heartbeats, and blocked sessions before they escalated into duplicate remediation or operator noise.

## Decision

We implement a real-time agent coordination map with JetStream KV as the preferred backing store and a repo-local file-backed fallback for offline tests and local tooling.

### Coordination contract

`platform.agent.coordination` is the runtime entry point. It provides:

- `AgentSessionEntry` as the normalized live session payload
- `AgentCoordinationStore` for snapshot, lookup, pruning, and deletion
- `AgentCoordinationSession` as a scoped publisher helper with heartbeat support

Each live session entry records:

- session identity and agent identity
- current phase, status, target, and progress
- heartbeat timestamps and expiry
- bounded coordination metadata such as held locks or blocked reason

When NATS is configured, the store uses JetStream KV and emits best-effort `platform.agent.state_updated` events. When NATS is unavailable, it falls back to a local JSON file under `.local/state/agent-coordination/`.

### First publishers

The first repository publishers are:

- the closure loop engine
- the Windmill observation-loop wrapper

These publishers create or refresh a coordination entry on phase changes and remove it on terminal completion so the map stays focused on active sessions.

### Read surfaces

The coordination map is exposed through:

- `GET /v1/platform/agents` on the authenticated platform API gateway
- a live `Agent Coordination` panel in the interactive ops portal
- the latest committed coordination snapshot receipt in the generated static ops portal

The repository also ships `scripts/agent_coordination_snapshot.py` so operators can inspect the current map locally and optionally write a receipt under `receipts/agent-coordination/`.

## Consequences

### Positive

- operators and agents now have one live read path for active multi-agent work
- stale sessions, blocked phases, and overlapping targets become visible earlier
- the gateway and portal surfaces share the same normalized coordination payload
- offline development and tests do not require a running JetStream dependency

### Trade-offs

- the coordination map is live state, not a historical replay log
- only the observation loop and closure loop publish on day one; other agent flows remain opt-in until they adopt the contract
- the JetStream-backed path adds a runtime dependency for the strongest cross-agent visibility

## Verification

The first implemented version verifies:

- coordination-store snapshot, filtering, expiry pruning, and terminal cleanup in tests
- authenticated gateway exposure at `/v1/platform/agents`
- interactive ops-portal rendering of live coordination entries
- generated static ops-portal rendering of the latest committed coordination snapshot receipt
- observation-loop and closure-loop coordination publishing through the shared store

## Related ADRs

- ADR 0058: NATS messaging backbone
- ADR 0092: Platform API gateway
- ADR 0093: Interactive operations portal
- ADR 0126: Observation loop verification model
- ADR 0130: Agent state persistence across workflow boundaries
- ADR 0131: Multi-agent handoffs
