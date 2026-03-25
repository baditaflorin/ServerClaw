# ADR 0153: Distributed Resource Lock Registry

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.149.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

The platform's current conflict detection mechanism (ADR 0127) operates at the **intent level**: before compiling an ExecutionIntent, the goal compiler queries the mutation ledger for other intents in `executing` or `pending_approval` states that touch the same service. If a conflict is found, the later intent is rejected and the caller must retry.

This model has three critical limitations for a multi-agent parallel workload:

**1. Ledger-based detection is too coarse.** The ledger records intents at the service level (`target_kind: service, target_id: netbox`). Two operations that target the same service but touch entirely different files (e.g., one rotates the Keycloak client secret, another updates the NetBox IPAM data model migration) will conflict in the ledger even though they are orthogonal in practice.

**2. There is no live resource map.** Conflict detection queries the ledger at intent-compile time. If Agent A's intent is in `executing` state and Agent B runs its bootstrap (ADR 0123) between A's compile and A's ledger write, B sees no conflict and both proceed — a race condition.

**3. No resource-level granularity.** The platform operates on typed resources: VM instances, Docker containers, Ansible host variables, configuration files, Postgres schemas, TLS certificates, DNS records, OpenBao paths. Two agents touching different resources within the same service should not conflict. Two agents touching the same Postgres schema — even for different services — should.

What is needed is a **resource lock registry**: a low-latency, real-time, resource-typed locking system that agents acquire before any mutation and release when done.

## Decision

We will implement a **distributed resource lock registry** backed by NATS JetStream Key-Value (KV) store, providing hierarchical, TTL-bounded, typed resource locks for all platform agents.

The first repository implementation lands in [`platform/locking/registry.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/locking/registry.py) as a worker-shared file-backed registry under the git common dir or `.local/state/`. It preserves the ADR contract that matters to callers now: typed locks, hierarchy checks, TTL expiry, and holder metadata that the deadlock detector can read. Optional NATS subject emission remains compatible with a later JetStream KV backend behind the same interface.

### Resource type hierarchy

Resources are typed and hierarchical. A lock on a parent resource blocks access to all its children:

```
platform:                    # Top-level; exclusive lock = full platform freeze
  vm:{vmid}                  # A specific Proxmox VM (e.g., vm:120)
    service:{svc_id}         # A service running in a VM (e.g., service:netbox)
      container:{name}       # A specific container (e.g., container:netbox_app)
      config:{path}          # A config file path (e.g., config:netbox/config.py)
      postgres:{schema}      # A Postgres schema (e.g., postgres:netbox)
      cert:{fqdn}            # A TLS certificate (e.g., cert:netbox.lv3.org)
    ansible:inventory        # The Ansible inventory (shared across services on a VM)
    ansible:host_vars:{host} # A specific host's vars file
  dns:zone                   # The Hetzner DNS zone
  openbao:path:{path}        # An OpenBao secret path
  nats:subject:{subject}     # A NATS subject namespace
```

### Lock types

| Type | Symbol | Semantics |
|---|---|---|
| `shared` | S | Multiple agents may hold simultaneously; blocks `exclusive` waiters |
| `exclusive` | X | Only one holder; blocks all other S and X attempts |
| `intent` | I | Declared future exclusive; blocks new X but not existing S (used during dry-run phase) |

This is a standard S/X/IX lock protocol. The typical pattern:
- An agent **planning** a change acquires an `intent` lock during dry-run.
- An agent **executing** a change upgrades to `exclusive` for the actual mutation.
- An agent **observing** acquires `shared` (non-blocking for read-heavy diagnostic agents).

### Implementation: NATS JetStream KV

```python
# platform/locking/registry.py

LOCK_KV_BUCKET = "platform.locks"  # NATS JetStream KV bucket; replicated, TTL-enabled

class ResourceLockRegistry:

    def acquire(
        self,
        resource_path: str,    # e.g., "vm:120/service:netbox/postgres:netbox"
        lock_type: LockType,   # shared | exclusive | intent
        holder: str,           # Agent identity (e.g., "agent/triage-loop/ctx:abc123")
        ttl_seconds: int = 300,
        wait_seconds: int = 0, # 0 = fail fast; > 0 = wait up to N seconds
    ) -> LockHandle:
        """
        Acquires a resource lock. Respects hierarchy: acquiring vm:120 checks
        for conflicting child locks; acquiring a child checks for conflicting
        parent locks.
        """
        entry = LockEntry(
            resource=resource_path,
            lock_type=lock_type,
            holder=holder,
            acquired_at=now(),
            expires_at=now() + timedelta(seconds=ttl_seconds),
            context_id=current_context().context_id,
        )
        key = sha256(resource_path)
        # Atomic CAS: only succeeds if no incompatible lock exists
        result = self.kv.update_if_expected(key, encode(entry), expected_revision=None)
        if not result.ok:
            if wait_seconds > 0:
                return self._wait_and_retry(resource_path, lock_type, holder, ttl_seconds, wait_seconds)
            raise ResourceLocked(resource_path, existing=result.current_holder)
        return LockHandle(entry, self)

    def release(self, handle: LockHandle):
        self.kv.delete(sha256(handle.resource), revision=handle.revision)
        # Notify the intent queue (ADR 0155) that this resource is now available
        nats.publish(f"platform.locks.released.{handle.resource}", {})
```

### Lock TTL and deadlock protection

Every lock has a mandatory TTL (max 10 minutes). If an agent crashes or is killed mid-execution, its locks expire automatically. The TTL is refreshed by a heartbeat published every 30 seconds by the holding agent:

```python
# Lock heartbeat — runs in a background thread within the agent's Windmill job
def _heartbeat(handle: LockHandle):
    while not handle.released:
        self.kv.update(handle.key, encode(handle.entry.refresh()), revision=handle.revision)
        time.sleep(30)
```

If the heartbeat misses two consecutive windows (60+ seconds with no refresh), the lock is considered abandoned. The deadlock detector (ADR 0162) scans for abandoned locks every 30 seconds.

### Ansible inventory shared lock

Ansible playbook runs require a special case: a playbook running `--limit netbox` and another running `--limit nginx` target different hosts but share the same inventory parse. The lock model handles this with scoped inventory locks:

```python
# Before running ansible-playbook
with registry.acquire("vm:120/ansible:host_vars:netbox-vm", LockType.EXCLUSIVE):
    with registry.acquire("vm:120/ansible:inventory", LockType.SHARED):
        run_ansible(playbook="netbox.yml", limit="netbox-vm")
```

Two agents can hold `shared` inventory locks simultaneously (both need to read inventory). Only a `--limit all` full-convergence run needs an `exclusive` inventory lock.

### Integration with goal compiler and conflict detector

The goal compiler (ADR 0112) acquires an `intent` lock during dry-run, upgrades to `exclusive` immediately before Windmill job submission, and records the lock handle in the ExecutionIntent:

```python
# In goal_compiler/compiler.py
class ExecutionIntent:
    lock_handles: list[LockHandle]  # New field: locks held for this intent

# Intent compile → acquire intent locks
intent_lock = registry.acquire(resource_for_intent(intent), LockType.INTENT, holder=actor_id)
intent.lock_handles = [intent_lock]

# Intent execute → upgrade to exclusive
for handle in intent.lock_handles:
    handle.upgrade(LockType.EXCLUSIVE)

# Intent complete/fail → release all locks
for handle in intent.lock_handles:
    handle.release()
```

The existing ledger-based conflict detector (ADR 0127) is **retained** as a semantic-level check (catches things the lock registry does not, like "don't restart netbox if its database is mid-migration"). The lock registry is the **real-time synchronisation** layer; the conflict detector is the **semantic safety** layer. Both must pass.

### Lock observability

All lock acquisitions, upgrades, releases, and expirations are published to NATS (`platform.locks.*`) and recorded in the real-time agent coordination map (ADR 0161). The ops portal (ADR 0093) displays active locks in a live view so operators can see at a glance which resources are held by which agents.

## Consequences

**Positive**

- The race condition where two agents both pass conflict detection on stale ledger data is eliminated. Lock acquisition is atomic and real-time, not based on a snapshot.
- Resource granularity enables true parallelism: two agents can simultaneously modify config files on different VMs, rotate certificates for different services, or run Ansible against different hosts — all without blocking each other.
- TTL-bounded locks ensure that a crashed agent never permanently blocks a resource. The platform self-heals within one TTL window (default: 5 minutes).

**Negative / Trade-offs**

- The NATS JetStream KV bucket is now on the critical path for every platform mutation. If the NATS broker is unavailable, no locks can be acquired and agents degrade to no-mutation mode (safe default).
- Lock granularity is a design decision that requires ongoing calibration. Too coarse (service-level locks only) and parallelism is lost; too fine (file-level locks only) and agents forget to lock parents.

## Related ADRs

- ADR 0044: Windmill (agent execution host; lock heartbeat runs in Windmill job context)
- ADR 0058: NATS event bus (JetStream KV backing store)
- ADR 0112: Deterministic goal compiler (acquires intent locks)
- ADR 0115: Event-sourced mutation ledger (semantic conflict layer; not replaced)
- ADR 0124: Platform event taxonomy (platform.locks.* events)
- ADR 0127: Intent conflict detection (semantic layer; complementary to this registry)
- ADR 0154: VM-scoped parallel execution lanes (lanes built on top of this registry)
- ADR 0155: Intent queue with release-triggered scheduling (subscribes to platform.locks.released)
- ADR 0161: Real-time agent coordination map (displays active lock state)
- ADR 0162: Distributed deadlock detection and resolution (scans lock registry for cycles)
