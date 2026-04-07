# ADR 0347: Agent File-Domain Locking for Atomic Infrastructure Mutations

- Status: Accepted
- Implementation Status: Not Implemented
- Date: 2026-04-05
- Scoping Note (2026-04-06): Implement as thin wrapper on existing ADR 0153 lock registry — map file domains to lock keys (e.g. file:vm:101:compose:keycloak). ~50 lines of Python extending platform/locking/registry.py, not a new system.
- Tags: agent-coordination, locking, atomicity, nginx, docker-compose, infrastructure

## Context

With tens of agents operating concurrently — some applying Ansible playbooks,
some modifying nginx upstream fragments, some rotating secrets, others
restarting services — shared infrastructure files are exposed to concurrent
writes with no coordination primitive in place.

The distributed resource lock registry (ADR 0153) exists and provides
hierarchical locking by resource type (`platform → vm → service → container`).
However, it does not model **file-domain ownership**, the specific concern that
arises when:

1. Two agents both need to write to a service's `docker-compose.yml` (e.g.,
   one adds a new env var, another rotates a secret).
2. One agent restarts the nginx reverse proxy while another is mid-way through
   writing a new `upstream` include fragment.
3. An apply agent runs `systemctl reload nginx` while a config agent has written
   an incomplete include file.

Without file-domain locking these races produce:
- Partial writes detected as valid configs by nginx — service outage.
- Docker Compose env file races — container launched with mixed old/new values.
- Secret rotation partial application — credentials mismatch between services.

The existing ADR 0153 lock types (`exclusive`, `shared`, `advisory`) and the
JetStream KV backing are the right primitive. What is missing is the **domain
taxonomy** that maps file paths to lock keys, and the **agent obligation** to
acquire the appropriate lock before writing.

## Decision

### 1. File-domain taxonomy

Every mutable infrastructure file belongs to exactly one **file domain**. A
file domain maps to a lock key in the ADR 0153 registry.

| Domain key pattern | Covers |
|---|---|
| `file:vm:<vmid>:nginx` | All nginx include fragments and reload for VMID |
| `file:vm:<vmid>:compose:<service>` | `docker-compose.yml` and `*.env` for service |
| `file:vm:<vmid>:certs` | Certificate files and renewal timers |
| `file:vm:<vmid>:firewall` | Firewall rule files (`*.fw`) |
| `file:host:proxmox:vm-config:<vmid>` | Proxmox VM config (`.conf` on PVE host) |
| `file:global:secrets` | OpenBao policies and agent HCL files |
| `file:global:inventory` | Ansible inventory and topology snapshot |

Sub-service specificity is preferred. An agent rotating a single service's
secret acquires `file:vm:101:compose:keycloak` not `file:vm:101:nginx`.

### 2. Lock acquisition protocol

Before writing to any file in a domain, an agent must:

1. Call `platform.locking.registry.acquire(domain_key, holder_id, lock_type,
   ttl_seconds)` where `holder_id` is the agent session ID (ADR 0161).
2. Perform all writes within the TTL. A standard TTL of 120 s is used for
   file writes; 300 s for full playbook apply operations.
3. Call `release(domain_key, holder_id)` when complete, or allow TTL expiry
   (which triggers an alert and automatic release after 1.5× TTL).

Lock type rules:
- **exclusive** — for any write that modifies an active config file.
- **shared** — for read-only inspection passes (diff, lint).
- **advisory** — for pre-flight checks that do not write.

### 3. Nginx reload gate

`systemctl reload nginx` (or `docker compose exec nginx nginx -s reload`) may
only be invoked by an agent that holds the exclusive lock on
`file:vm:<vmid>:nginx`.

A dedicated Ansible task file `tasks/nginx_reload_gated.yml` wraps the reload
with a lock check assertion. All roles that trigger nginx reload must include
this task file instead of calling the systemd/docker reload directly.

```yaml
# tasks/nginx_reload_gated.yml
- name: Assert nginx file-domain lock is held by this session
  ansible.builtin.assert:
    that:
      - agent_session_id is defined
      - agent_nginx_lock_held | default(false) | bool
    fail_msg: >
      Nginx reload attempted without file-domain lock.
      Session {{ agent_session_id }} must acquire file:vm:{{ target_vmid }}:nginx first.
```

### 4. Compose write gate

The `common` role's `openbao_compose_env.yml` and any role that renders a
`docker-compose.yml.j2` template must:

1. Set `agent_compose_lock_held: true` only after lock acquisition.
2. Use a `rescue` block to release the lock if the template task fails.
3. Run `docker compose up -d --no-deps <service>` only inside the lock scope.

### 5. Lock telemetry

Every lock acquisition and release emits a structured event to the
`platform.locks.file_domain` NATS subject:

```json
{
  "event": "acquired",
  "domain": "file:vm:101:compose:keycloak",
  "holder": "agent-session-abc123",
  "workstream": "ws-0346",
  "adr": "0346",
  "ttl_seconds": 120,
  "timestamp": "2026-04-05T10:00:00Z"
}
```

This allows the agent coordination map (ADR 0161) and Grafana dashboards to
show live lock contention in real time.

### 6. Deadlock avoidance rule

Agents must acquire file-domain locks in **ascending domain key lexicographic
order** when they need multiple locks. This is the canonical total ordering
that prevents circular waits. An agent that needs both
`file:vm:101:compose:keycloak` and `file:vm:101:nginx` must acquire the compose
lock first.

## Places That Need to Change

### `platform/locking/registry.py`

Add `FILE_DOMAIN` resource type to the resource hierarchy enum. Validate that
file-domain key strings match the `file:<scope>:<vmid>:<subdomain>` pattern.

### `roles/common/tasks/`

Add `file_domain_lock_acquire.yml` and `file_domain_lock_release.yml` task
files that call a thin Python wrapper script `scripts/file_domain_lock.py`.

### `scripts/file_domain_lock.py` (new)

CLI tool conforming to ADR 0343 operator tool contract. Commands:
`acquire`, `release`, `status`. Exits 0 (acquired), 1 (error), 2 (no-op/already held by self).

### `roles/*/tasks/main.yml` — all roles that write compose or nginx files

Wrap file-writing task blocks with `file_domain_lock_acquire.yml` /
`file_domain_lock_release.yml` includes.

### `tasks/nginx_reload_gated.yml` (new)

Gate file as described above.

### `docs/runbooks/file-domain-locking.md` (new)

Operator runbook: how to inspect held locks, force-release a stuck lock, and
diagnose lock timeout alerts.

## Consequences

### Positive

- Concurrent agents cannot produce partial/corrupt nginx or Compose configs.
- Lock telemetry gives real-time visibility into which agent is modifying what.
- Deadlock avoidance rule is checkable by the `detect-deadlocks.py` script
  (ADR 0162) extended to the `FILE_DOMAIN` resource type.

### Negative / Trade-offs

- Every role that writes files must be updated to acquire/release locks —
  a large surface but mechanical change.
- Lock acquisition adds ~50–200 ms of JetStream round-trip per operation.
- Agents that crash without releasing locks leave locks held until TTL; alerts
  must be tuned to avoid false positives on short operations.

## Related ADRs

- ADR 0153: Distributed Resource Lock Registry
- ADR 0161: Real-Time Agent Coordination Map
- ADR 0162: Distributed Deadlock Detection and Resolution
- ADR 0329: Shared Docker Runtime Bridge Chain Checks Must Fail-Safe Before Daemon Restart
- ADR 0343: Operator Tool Interface Contract
