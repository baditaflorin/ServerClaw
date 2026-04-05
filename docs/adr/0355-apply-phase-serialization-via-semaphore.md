# ADR 0355: Apply-Phase Serialization via Resource-Group Semaphore

- Status: Accepted
- Implementation Status: Not Implemented
- Date: 2026-04-05
- Tags: agent-coordination, locking, semaphore, apply-safety, atomicity

## Context

ADR 0347 (File-Domain Locking) serializes writes at the individual file level.
ADR 0349 (Capability Manifest) enables agents to detect peer conflicts before
starting work. However, neither mechanism prevents a more coarse-grained
problem: **two apply agents running full playbooks against the same VM
concurrently**.

A full apply playbook (`playbooks/keycloak.yml`) may:
1. Write multiple files (compose, env, certs, nginx fragment).
2. Restart multiple containers.
3. Reload nginx.
4. Rotate secrets.

Each individual operation can acquire its file-domain lock. But the
*combination* — a full service apply — is not atomic at the playbook level.
If two apply agents target the same VM at the same time, they interleave lock
acquisitions across multiple domains, creating:

- **Lock order inversions:** agent A acquires compose then nginx; agent B
  acquires nginx then compose. Both can block each other without a formal
  deadlock (the cycle detector handles this) but the resolution introduces
  retry latency.
- **State inconsistency windows:** a service is half-applied (new compose,
  old env) while the second agent is writing the env. Health checks pass
  the compose check but fail the env check during the window.
- **Double restart amplification:** both agents each trigger a service
  restart. Two restarts in quick succession cause unnecessary downtime and
  confusing audit trails.

A resource-group semaphore addresses this by limiting concurrent full-apply
operations on a given resource group (VM or service) to a configurable count
(default: 1).

## Decision

### 1. Resource groups

A **resource group** is a named set of resources that share a single
apply-phase semaphore:

| Group name | Resources covered |
|---|---|
| `vm:<vmid>` | All services on the given VM |
| `service:<name>` | A specific named service across all VMs |
| `postgres-ha` | The HA Postgres cluster and all database roles |
| `networking` | nginx VMs, api-gateway, public-edge, firewall rules |
| `secrets` | OpenBao and all secret rotation operations |
| `certs` | step-ca and all certificate renewal operations |

The `vm:<vmid>` group is the most common. Apply agents targeting a single VM
always acquire the `vm:<vmid>` semaphore.

### 2. Semaphore implementation

The semaphore is backed by the JetStream KV store (same backing as ADR 0153).
Key: `semaphore.apply.<group>`.

```python
@dataclass
class ApplySemaphore:
    group: str
    max_concurrent: int = 1          # configurable per group
    holder_session_id: str = ""
    holder_workstream: str = ""
    acquired_at: str = ""
    ttl_seconds: int = 900           # 15 min default; extended on progress
    expires_at: str = ""
```

Operations:
- `acquire(group, session_id, workstream, ttl)` — atomic CAS on KV key. Returns
  True if acquired, False if held by another session. Retries with backoff
  for up to `wait_timeout_seconds` (default: 120 s).
- `release(group, session_id)` — validates holder matches, deletes key.
- `extend(group, session_id, ttl)` — extends TTL on active semaphore.
- `status(group)` — returns current holder or `{"status": "free"}`.

### 3. Apply agent protocol

All playbooks that perform full-service applies must:

1. Declare their resource group(s) in the capability manifest `declared_domains`
   (ADR 0349).
2. Execute `preflight_peer_conflict_check.yml` (ADR 0349).
3. **Acquire the semaphore** for each resource group:

```yaml
# tasks/apply_semaphore_acquire.yml
- name: Acquire apply-phase semaphore for {{ resource_group }}
  ansible.builtin.command: >
    python3 scripts/apply_semaphore.py acquire
    --group {{ resource_group }}
    --session {{ agent_session_id }}
    --workstream {{ workstream_id }}
    --wait-timeout 120
  register: semaphore_result
  failed_when: semaphore_result.rc == 1
  changed_when: false

- name: Fail if semaphore not acquired within timeout
  ansible.builtin.fail:
    msg: >
      Could not acquire semaphore for {{ resource_group }} within 120s.
      Current holder: {{ (semaphore_result.stdout | from_json).holder_session_id }}
      Workstream: {{ (semaphore_result.stdout | from_json).holder_workstream }}
  when: semaphore_result.rc == 2
```

4. Run the full apply (all file writes, restarts, reloads).
5. **Release the semaphore** in an `always:` block.

The semaphore extends its TTL every 60 seconds via a background heartbeat
task (`async: 60, poll: 0`) that runs during the apply.

### 4. Semaphore configuration

`config/apply-semaphores.yaml`:

```yaml
groups:
  vm:101: { max_concurrent: 1, ttl_seconds: 900 }
  vm:102: { max_concurrent: 1, ttl_seconds: 900 }
  postgres-ha: { max_concurrent: 1, ttl_seconds: 1800 }
  networking: { max_concurrent: 1, ttl_seconds: 600 }
  secrets: { max_concurrent: 2, ttl_seconds: 300 }   # rotation can be parallel
  certs: { max_concurrent: 3, ttl_seconds: 300 }     # cert renewal is read-safe
```

`max_concurrent: 2` for `secrets` means two independent secret rotation jobs
can run in parallel (different service secrets). The file-domain lock (ADR 0347)
ensures they do not write the same compose env file simultaneously.

### 5. Observability and alerting

`scripts/apply_semaphore.py status --all` outputs all group statuses with
holder info. This is added to the platform health dashboard.

Alert triggers:
- Semaphore held for `> 1.5× ttl_seconds` without TTL extension → stuck agent
  alert via ntfy.
- Semaphore acquired by session with no active capability manifest → orphan
  lock alert.

### 6. Deadlock prevention with semaphore ordering

Agents that need multiple resource-group semaphores must acquire them in
alphabetical order by group name — consistent with the file-domain lock
ordering rule (ADR 0347). This ensures no circular waits across the two
locking layers.

## Places That Need to Change

### `scripts/apply_semaphore.py` (new)

Layer 1 tool per ADR 0345. Commands: `acquire`, `release`, `extend`, `status`.
Reads `config/apply-semaphores.yaml` for group configuration.

### `config/apply-semaphores.yaml` (new)

Group configuration as above.

### `roles/common/tasks/apply_semaphore_acquire.yml` (new)
### `roles/common/tasks/apply_semaphore_release.yml` (new)

Standard task files included by all full-apply playbooks.

### All service playbooks (`playbooks/*.yml`)

Add semaphore acquire at the top and release in `always:` block.

### `platform/locking/registry.py`

Add `APPLY_SEMAPHORE` resource type. Semaphore uses same KV backing as lock
registry but different key prefix.

### Grafana dashboard

Extend `Platform / Agent Mutation Audit` (ADR 0354) with semaphore
contention panel: queue depth per group, wait time histogram.

## Consequences

### Positive

- Full playbook applies against a VM are serialized. No more interleaved
  applies with overlapping lock acquisition.
- The audit trail shows exactly when each apply started, who held the
  semaphore, and how long it ran.
- Double-restart is eliminated: second agent waits, then checks idempotent
  state and exits as no-op.

### Negative / Trade-offs

- Agents must wait up to `wait_timeout_seconds` for the semaphore. Long-running
  applies (>15 min) must extend the TTL or the next agent wrongly assumes the
  semaphore is stale.
- `max_concurrent: 1` for most VM groups means throughput is limited when many
  agents target the same VM. This is intentional — safety over parallelism —
  but operators must plan accordingly.
- A crashed agent that holds the semaphore blocks all subsequent applies until
  the TTL expires (up to 900 s). TTL must be tuned conservatively.

## Related ADRs

- ADR 0131: Multi-Agent Handoff Protocol
- ADR 0153: Distributed Resource Lock Registry
- ADR 0161: Real-Time Agent Coordination Map
- ADR 0162: Distributed Deadlock Detection and Resolution
- ADR 0343: Operator Tool Interface Contract
- ADR 0345: Layered Operator Tool Separation
- ADR 0347: Agent File-Domain Locking
- ADR 0349: Agent Capability Manifest and Peer Discovery
- ADR 0354: Structured Agent Mutation Audit Log
