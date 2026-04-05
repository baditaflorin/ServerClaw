# ADR 0349: Agent Capability Manifest and Peer Discovery

- Status: Accepted
- Implementation Status: Not Implemented
- Date: 2026-04-05
- Tags: agent-coordination, agent-discovery, capability-manifest, peer-awareness, nats

## Context

The platform supports tens of agents operating in parallel: apply agents,
config-diff agents, secret rotation agents, nginx config agents, monitoring
agents, and LLM-driven automation agents. Each agent is aware of its own task
but has no reliable way to know:

- Which other agents are currently running.
- What resource domains (file-domains, VMs, services) those agents are
  operating on.
- Whether a peer agent is in the middle of a potentially conflicting operation.
- What capabilities (playbooks, domains, tools) a peer is authorized to use.

ADR 0161 (Real-Time Agent Coordination Map) defines the `AgentSessionEntry`
payload and JetStream KV backing for session state. However, it does not define
**capability declaration** — the set of operations an agent is allowed to
perform. Without capability declaration, the coordination map shows *who is
running* but not *what they are allowed to touch*, making conflict prediction
impossible.

ADR 0069 (Agent Tool Registry) defines which tools agents may invoke. But tool
registry entries are static configuration; they do not reflect runtime
capability of a specific agent session.

The result: agents avoid conflicts only by acquiring locks after the fact
(ADR 0153, ADR 0347). A higher-level mechanism that allows agents to signal
capability upfront — before acquiring locks — would allow agents to avoid
work queuing, detect infeasible parallel plans, and coordinate without polling.

## Decision

### 1. Capability manifest schema

Every agent session publishes a **capability manifest** alongside its
`AgentSessionEntry` in the JetStream KV store (ADR 0161). The manifest is
stored under key `agent.capabilities.<session_id>` and has the following schema:

```yaml
schema_version: 1
session_id: "agent-session-abc123"
agent_role: "apply"          # apply | config-diff | secret-rotation | nginx | monitor | llm
workstream: "ws-0346"
adr_authority: ["0346", "0347"]   # ADRs authorizing this agent's actions this session
started_at: "2026-04-05T10:00:00Z"
ttl_seconds: 600

# Declared resource domains this agent MAY touch (superset of what it will lock)
declared_domains:
  - "file:vm:101:compose:keycloak"
  - "file:vm:101:nginx"

# Playbooks this agent is authorized to run
declared_playbooks:
  - "playbooks/keycloak.yml"
  - "playbooks/services/keycloak.yml"

# Services this agent may restart
declared_restarts:
  - vmid: 101
    service: keycloak

# Whether this agent emits mutations (false = read-only / observability agent)
mutates: true
```

### 2. Manifest lifecycle

| Event | Action |
|---|---|
| Agent session starts | Publish manifest to `agent.capabilities.<session_id>` with TTL |
| Agent acquires a domain lock (ADR 0347) | Confirm domain is listed in `declared_domains` |
| Agent exits cleanly | Delete manifest key |
| Agent crashes / TTL expires | JetStream TTL auto-deletes manifest; coordination map cleanup runs |

An agent that attempts to acquire a lock for a domain **not listed** in its
manifest emits a warning and extends its manifest before proceeding. This
is an escape hatch for dynamic workflows, but the extension is recorded in
the audit log (ADR 0354).

### 3. Peer discovery API

`scripts/agent_peer_discovery.py` (new, Layer 1 per ADR 0345):

```
agent_peer_discovery.py list                     # all active sessions + capabilities
agent_peer_discovery.py query --domain <key>     # sessions that declared <key>
agent_peer_discovery.py query --playbook <path>  # sessions running given playbook
agent_peer_discovery.py query --service <name>   # sessions touching given service
agent_peer_discovery.py conflicts --my-manifest <path>  # detect conflicts with self
```

Output: JSON per ADR 0343 contract.

### 4. Pre-flight conflict check

Agents that are in the **apply** or **secret-rotation** role must run a
pre-flight conflict check before acquiring any locks:

```yaml
# tasks/preflight_peer_conflict_check.yml
- name: Check for peer agent conflicts
  ansible.builtin.command: >
    python3 scripts/agent_peer_discovery.py conflicts
    --my-manifest "{{ agent_manifest_path }}"
  register: conflict_check
  failed_when: conflict_check.rc == 1
  changed_when: false

- name: Abort if peers declare overlapping domains
  ansible.builtin.fail:
    msg: "Peer conflict detected: {{ (conflict_check.stdout | from_json).conflicts }}"
  when: (conflict_check.stdout | from_json).conflicts | length > 0
```

Read-only agents (observability, diff) skip this check.

### 5. Conflict detection algorithm

Two agents conflict if their `declared_domains` sets have a non-empty
intersection AND both have `mutates: true`. Adjacent-domain conflicts (e.g.,
one agent holds `file:vm:101:compose:keycloak` and another holds
`file:vm:101:nginx`) are flagged as **advisory** — not fatal — because the
domains are disjoint but the same VM is affected. Advisory conflicts are logged
and surfaced in the coordination map dashboard without blocking.

### 6. Coordination map integration

The coordination map runbook (ADR 0161) and Grafana dashboard are extended to:
- Show declared domains per session (color-coded by domain overlap risk).
- Show advisory conflict indicators between sessions with overlapping VMs.
- Show a timeline of manifest publish/delete events.

## Places That Need to Change

### `platform/agent/session.py`

Add `CapabilityManifest` dataclass. Add `publish_manifest(session_id, manifest)`
and `delete_manifest(session_id)` functions using the JetStream KV store.

### `scripts/agent_peer_discovery.py` (new)

Layer 1 tool per ADR 0345. Implements `list`, `query`, `conflicts` subcommands.
Reads from JetStream KV; falls back to `.local/state/agent-capabilities/` JSON
files when JetStream is unavailable.

### `roles/common/tasks/preflight.yml`

Import `preflight_peer_conflict_check.yml` for apply-role agents.

### `roles/common/tasks/main.yml`

Add manifest publish at session start and delete on `always` cleanup block.

### `config/agent-policies.yaml`

Add `declared_domains` and `declared_playbooks` fields to agent policy entries.
Policies now serve as the authorization source for manifest validation.

### `docs/runbooks/agent-capability-manifest.md` (new)

Operator runbook for inspecting active manifests, diagnosing conflict blocks,
and force-clearing a stale manifest.

## Consequences

### Positive

- Agents detect scheduling conflicts before acquiring locks — reducing wasted
  work and lock contention.
- Operators can inspect the full capability picture of all running agents from
  a single `agent_peer_discovery.py list` call.
- The manifest acts as a self-documenting record of what each agent session
  was authorized to do — searchable in the audit log.

### Negative / Trade-offs

- Agents that fail to publish their manifest (crash at start) are invisible to
  peer discovery — the system degrades to lock-only coordination, not fails.
- `declared_domains` is a pre-declared superset; agents may declare more than
  they use. Overly broad declarations reduce the value of conflict detection.
- JetStream dependency for peer discovery: if NATS is down, peer discovery
  falls back to file-backed state which may be stale.

## Related ADRs

- ADR 0069: Agent Tool Registry and Governed Tool Calls
- ADR 0130: Agent State Store
- ADR 0153: Distributed Resource Lock Registry
- ADR 0161: Real-Time Agent Coordination Map
- ADR 0162: Distributed Deadlock Detection and Resolution
- ADR 0167: Agent Handoff and Context Preservation
- ADR 0343: Operator Tool Interface Contract
- ADR 0345: Layered Operator Tool Separation
- ADR 0347: Agent File-Domain Locking for Atomic Infrastructure Mutations
