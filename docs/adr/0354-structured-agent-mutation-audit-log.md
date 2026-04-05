# ADR 0354: Structured Agent Mutation Audit Log

- Status: Accepted
- Implementation Status: Not Implemented
- Date: 2026-04-05
- Tags: audit, agent-coordination, observability, compliance, mutation-tracking

## Context

The `plugins/callback/mutation_audit.py` callback plugin records Ansible task
events but produces output tied to a single playbook run. There is no
consolidated, queryable audit trail across:

- Multiple parallel agent sessions.
- Operator tool invocations (`scripts/*.py`) that run outside Ansible.
- Secret rotations that occur via OpenBao agent.
- Docker service restarts and container lifecycle events.
- File mutations that happen via shell tasks (not Ansible modules).

Specific gaps:

1. **Cross-session audit.** When two agents run concurrently, their Ansible
   callback logs are in separate files. Correlating "which agent changed what
   and in what order" requires manual log stitching.

2. **Tool-level audit.** `coolify_tool.py`, `proxmox_tool.py`, and other
   operator tools (ADR 0343) produce JSON stdout per the contract, but this
   output is not persisted to a durable audit log — it goes only to the
   calling process.

3. **ADR linkage.** Current logs do not record which ADR authorized a given
   change. Compliance queries like "show all changes made under ADR 0340
   authority" are not answerable from current data.

4. **Workstream linkage.** Changes are not linked to workstream IDs in the
   current callback log. The connection exists in workstream docs but not in
   machine-readable operational data.

## Decision

### 1. Mutation event schema

Every agent mutation produces a **mutation event** — a structured JSON record
emitted to a durable log. The schema:

```json
{
  "schema_version": 1,
  "event_id": "evt-uuid4",
  "timestamp": "2026-04-05T10:00:00Z",
  "agent_session_id": "agent-session-abc123",
  "agent_role": "apply",
  "workstream": "ws-0346",
  "adr_authority": ["0346", "0349"],
  "operator": "human-operator | automated",

  "mutation": {
    "type": "file_write | service_restart | secret_rotation | vm_config | docker_pull | compose_up | nginx_reload | firewall_rule",
    "target_vmid": 101,
    "target_service": "keycloak",
    "resource": "file:vm:101:compose:keycloak",
    "description": "Rendered runtime.env from openbao secrets",
    "idempotent": true,
    "changed": true
  },

  "outcome": {
    "status": "success | failure | no_op",
    "exit_code": 0,
    "duration_ms": 1240,
    "error": null
  },

  "context": {
    "playbook": "playbooks/services/keycloak.yml",
    "task": "Render keycloak runtime env",
    "ansible_host": "keycloak-vm",
    "git_sha": "b980bb92e"
  }
}
```

### 2. Emission points

| Source | Emission mechanism |
|---|---|
| Ansible playbook tasks | `mutation_audit.py` callback plugin (updated) |
| Operator tools (`scripts/*.py`) | `controller_automation_toolkit.emit_mutation_event()` |
| Secret rotation playbooks | Dedicated `emit_event` task |
| Docker compose operations | `common` role `docker_compose_up` task wrapper |
| Nginx reload gate | `nginx_reload_gated.yml` task (ADR 0347) |

### 3. Storage backends

Events are written to two backends (both, always):

**A. Loki** — primary queryable store:
- Label set: `{job="mutation-audit", workstream=<ws>, adr=<adr>, service=<svc>}`
- Retention: 180 days.
- Query: `{job="mutation-audit", workstream="ws-0346"} | json | changed=true`

**B. NATS JetStream subject `platform.audit.mutations`** — real-time bus:
- Durable consumer `audit-archive` saves to local file fallback
  `.local/state/audit/mutations/YYYY-MM-DD.jsonl`.
- Retention: 30 days in JetStream; files kept 90 days.

Both backends are append-only. No mutation event may be deleted or modified
after emission. Loki and NATS are both treated as immutable audit sinks.

### 4. Ansible callback plugin update

`plugins/callback/mutation_audit.py` is updated to:
- Emit a mutation event for every `changed=True` Ansible task.
- Include `workstream_id` and `adr_authority` from playbook vars
  (`workstream_id | default('unset')`, `adr_authority | default([])`).
- Emit to both Loki (via HTTP push) and NATS subject.
- Fall back to local JSONL file if both backends are unavailable.

### 5. Operator tool integration

`controller_automation_toolkit.py` gains:

```python
def emit_mutation_event(mutation: dict, outcome: dict, context: dict) -> None:
    """Emit a structured mutation event to audit backends."""
    event = build_mutation_event(mutation, outcome, context)
    _emit_to_nats(event)   # fire-and-forget, does not block tool exit
    _append_to_local_log(event)
```

All contract-compliant tools (ADR 0343) call this after each state change.

### 6. Query interface

`scripts/audit_query.py` (new):

```
audit_query.py recent --hours 24                    # last 24h of mutations
audit_query.py by-workstream --ws ws-0346           # all events for workstream
audit_query.py by-adr --adr 0346                    # all events under ADR authority
audit_query.py by-service --service keycloak        # keycloak mutations only
audit_query.py by-session --session <id>            # single agent session
audit_query.py failures --hours 24                  # failed mutations only
```

Reads from local JSONL fallback. When Loki is available, proxies to Loki
LogQL queries for longer time ranges.

### 7. Grafana dashboard

A new Grafana panel `Platform / Agent Mutation Audit` shows:
- Mutations per hour by agent role.
- Mutation success/failure ratio.
- Top 10 changed services (last 24h).
- Active workstream mutation heatmap.

Alert: if `failure` events exceed 5% of total mutations in a 15-minute window,
notify via ntfy.

## Places That Need to Change

### `plugins/callback/mutation_audit.py`

Update to emit full mutation event schema. Add NATS and Loki emit paths.
Add fallback JSONL write.

### `controller_automation_toolkit.py`

Add `emit_mutation_event()`, `build_mutation_event()`, `_emit_to_nats()`,
`_append_to_local_log()`.

### `scripts/audit_query.py` (new)

Layer 1 tool. Implements `recent`, `by-workstream`, `by-adr`, `by-service`,
`by-session`, `failures` subcommands.

### `roles/common/tasks/docker_compose_up.yml` (updated)

Wrap `docker compose up -d` invocation with mutation event emission.

### `playbooks/tasks/notify.yml`

Extend to emit a summary mutation event when a playbook run completes.

### Grafana configuration (new dashboard JSON)

Add `Platform / Agent Mutation Audit` dashboard to the monitoring stack role.

### `docs/runbooks/mutation-audit-log.md` (new)

How to query, interpret, and export audit log. Compliance section for audit
review procedures.

## Consequences

### Positive

- Complete, cross-session, queryable audit trail for every infrastructure
  mutation, linked to ADR and workstream.
- Compliance queries ("what changed under ADR 0340 authority?") are
  answerable in seconds via `audit_query.py`.
- Failure rate alerting gives early warning of systemic apply problems.

### Negative / Trade-offs

- Every mutation now has an async NATS/Loki emit call — adds ~10–50 ms
  of I/O per mutating task (fire-and-forget, does not block).
- Local JSONL fallback can grow large on high-apply-frequency deployments;
  rotation policy needed.
- Event schema versioning: if schema changes, old events in Loki/JSONL
  may not parse cleanly with new `audit_query.py` versions.
- Loki push from Ansible requires the Loki push endpoint to be reachable
  from the controller host — a new network dependency.

## Related ADRs

- ADR 0069: Agent Tool Registry and Governed Tool Calls
- ADR 0130: Agent State Store
- ADR 0153: Distributed Resource Lock Registry
- ADR 0161: Real-Time Agent Coordination Map
- ADR 0343: Operator Tool Interface Contract
- ADR 0347: Agent File-Domain Locking
- ADR 0349: Agent Capability Manifest and Peer Discovery
- ADR 0351: Change Provenance Tagging
