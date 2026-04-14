# ADR 0417: Service VM Migration IaC — Single Canonical Procedure

**Date:** 2026-04-14
**Status:** Implemented
**Related:** ADR 0323 (Service Mobility Tiers), ADR 0373 (Service Registry), ADR 0396 (Service Decommissioning), ADR 0416 (Topology Consistency Enforcement)

---

## Context

### The Problem This Solves

ADR 0416 established a topology consistency validator that catches drift *after it
has already been committed*. ADR 0416's Section 4 documented a manual 5-step
operator runbook for VM migrations:

> 1. Update platform_service_registry.host_group
> 2. Update platform_postgres_clients.source_vm
> 3. Update lv3_service_topology.owning_vm
> 4. Run validate_topology_consistency.py --check
> 5. Converge affected services in sequence

This runbook has three failure modes:
1. **Operators skip or misorder steps** — there is no enforcement that all four registries are updated together, or that the converge order (postgres → stop-old → service → nginx) is followed.
2. **No single place to find "how to migrate a service"** — operators invent their own procedures, resulting in 10 ways to do the same thing.
3. **Old containers accumulate** — when a service moves, the container on the old VM is rarely removed. There is no tooling to detect or clean these up.

Three topology drift incidents in 72 hours (ADR 0416) confirmed that manual
multi-step procedures are not reliable. The ADR 0416 postmortem identified the
immediate fix (validator + gate); this ADR is the systemic fix.

### Scope

This ADR covers:
- Moving a running service from one VM to another
- Cleaning up containers left behind by previous migrations
- Testable, dry-run-capable procedures that operators can verify before executing

This ADR does NOT cover:
- Decommissioning a service permanently (ADR 0396)
- Commissioning a new service from scratch (ADR 0373)
- Horizontal scaling / running a service on multiple VMs simultaneously (future)

---

## Decision

### 1. `migrate_service.py` is the single canonical migration entrypoint

```bash
# Preview: show ordered plan without touching anything
make migrate-service-dry-run svc=keycloak to=runtime-control

# Execute: update registries + run ordered converges + write receipt
make migrate-service svc=keycloak to=runtime-control env=production
```

Manual multi-step migrations (editing files individually, running converges by hand
in an operator-chosen order) are deprecated. The script enforces correctness by:
- Updating **all registry fields** that encode VM assignment atomically
- Running converges in the **correct dependency order**
- Writing a **migration receipt** for auditability

The script is the machine-readable form of the operator runbook. The runbook now
IS the script.

### 2. Registry fields updated atomically

When `svc` migrates from `old-vm` to `new-vm`, the script updates:

| File | Field | Change |
|------|-------|--------|
| `inventory/group_vars/all/platform_services.yml` | `host_group` | `old-vm` → `new-vm` |
| `inventory/group_vars/all/platform_services.yml` | `proxy.upstream_host` | `old-vm` → `new-vm` |
| `inventory/host_vars/proxmox-host.yml` | `lv3_service_topology[svc].owning_vm` | `old-vm` → `new-vm` |
| `inventory/host_vars/proxmox-host.yml` | Jinja2 VM refs in topology block | `'old-vm'` → `'new-vm'` |

`platform_service_registry.host_group` remains the authoritative single source of
truth (ADR 0416). The other fields are derivatives that the script keeps in sync.

After file edits, `validate_topology_consistency.py --check` is run as a guard.
If any field was missed (e.g. a new registry format not yet handled), the check
catches it and aborts before any converge runs.

### 3. Ordered converge sequence

```
registry update → topology validation → postgres-vm → stop-old → converge-svc → nginx-edge
```

| Step | Condition | Rationale |
|------|-----------|-----------|
| Registry update | Always | Single source of truth must change first |
| Topology validation | Always | Guard: fail fast if any field was missed |
| `converge-postgres-vm` | If svc uses postgres | pg_hba.conf must allow new VM BEFORE service starts |
| `teardown-service svc=X on_vm=old-vm` | Always | Stop old container; idempotent if not running |
| `converge-svc` | Always | Start service on new VM |
| `converge-nginx-edge` | If svc has proxy or topology entry | Update upstream to new VM |

**Why postgres before service?** If the service starts on the new VM before
pg_hba.conf is updated, every DB connection attempt fails. This was the exact
failure mode in the ADR 0416 incident.

**Why stop-old before converge-new?** Prevents split-brain: both VMs running
the same service simultaneously (double-write, session conflicts, port conflicts
if port numbers collide on future VM-reuse).

**Why nginx after service?** Traffic should only route to the new VM once the
service is healthy. nginx converge happens last.

### 4. Teardown playbook — generic, reusable

`playbooks/services/_teardown_service.yml` accepts `teardown_host` and
`teardown_container_name` as extra-vars. It:
- Checks if the container exists
- Stops and removes it if found
- Logs a no-op message if it was already gone (idempotent)

Available standalone:
```bash
make teardown-service svc=keycloak on_vm=docker-runtime env=production
# with override: make teardown-service svc=keycloak on_vm=docker-runtime container_name=my-custom-name
```

### 5. Orphan detection and cleanup

```bash
# List containers running on the wrong VM
make detect-orphans

# Stop and remove all detected orphans
make purge-orphans
```

`scripts/detect_orphaned_containers.py` SSHes to every docker-capable VM in
`platform_guest_catalog`, runs `docker ps`, and compares against the registry.

**Testable without SSH** — pass `--mock fixtures/docker-ps.json` to load mock
`docker ps` output: `{vm_name: [container_name, ...]}`. The comparison logic is
fully unit-testable without network access.

```bash
# Example mock test:
echo '{"docker-runtime": ["lv3-mail-stalwart", "lv3-mail-gateway"]}' > /tmp/mock-ps.json
python scripts/detect_orphaned_containers.py --list --mock /tmp/mock-ps.json
```

### 6. Testability contract

| Test | How |
|------|-----|
| Dry-run plan (no side effects) | `make migrate-service-dry-run svc=X to=Y` |
| Registry update logic | Unit test: call `update_platform_services()` on a fixture YAML, assert changes |
| Converge order validation | Unit test: `build_migration_plan()` with mock registry data |
| Orphan detection | `detect_orphaned_containers.py --mock <json>` |
| Full migration gate | `validate_topology_consistency.py --check` after migration |

### 7. Enforceability

- **Pre-push gate** already rejects topology drift (ADR 0416). This means: if an operator
  manually edits one file but not the others, the gate catches it.
- The migration script's value is that it makes the correct (multi-file) edit atomically —
  operators who use it will never fail the gate.
- Operators who bypass the script and edit files manually are still subject to the gate.
  There is no "override" for the gate on topology drift.

---

## Consequences

### Positive

- One command to move a service: `make migrate-service svc=X to=Y`
- Ordered converge sequence is machine-enforced, not human-remembered
- Orphaned containers are detectable and cleanable with a single command
- Dry-run mode lets operators preview changes safely before executing
- Receipt written to `receipts/migrations/` for every migration
- All logic is testable without SSH (mock fixtures, dry-run)

### Negative

- The migration script does NOT automatically commit the registry changes.
  The operator must `git diff`, review, and `git commit` after migration.
  (This is intentional — operators should review what changed.)
- The Jinja2 template replacement in proxmox-host.yml uses regex; unusual
  template patterns may not be caught. The topology validator will catch any
  missed fields.
- Orphan detection requires SSH access to production VMs; cannot run in CI gate.

### Neutral

- ADR 0416 Section 4 (operator procedure) is superseded by this ADR.
  The manual runbook now redirects to `make migrate-service`.
- ADR 0323 (Service Mobility Tiers) defines whether a service IS movable;
  this ADR defines HOW to move it once that decision is made.

---

## Files Added / Modified

| File | Change |
|------|--------|
| `scripts/migrate_service.py` | New — canonical migration orchestrator |
| `scripts/detect_orphaned_containers.py` | New — orphan detection and cleanup |
| `playbooks/services/_teardown_service.yml` | New — generic container stop/remove playbook |
| `Makefile` | Added: `migrate-service`, `migrate-service-dry-run`, `teardown-service`, `detect-orphans`, `purge-orphans` |
| `docs/adr/0416-topology-consistency-enforcement.md` | Section 4 updated to point to `make migrate-service` |

---

## Example: Full migration walk-through

```bash
# 1. Preview the plan (no changes made)
make migrate-service-dry-run svc=gitea to=runtime-control

# Output:
# MIGRATION PLAN: gitea  docker-runtime → runtime-control  [env=production]
# ─────────────────────────────────────────────────────────────────────
# [Registry changes — would apply]
#   platform_services.yml  gitea.host_group: docker-runtime → runtime-control
#   platform_services.yml  gitea.proxy.upstream_host: docker-runtime → runtime-control
#   proxmox-host.yml      lv3_service_topology.gitea: all refs 'docker-runtime' → 'runtime-control'
# Converge sequence (4 steps):
#   1. Validate topology consistency (ADR 0416)
#      $ validate_topology_consistency.py --check
#   2. Stop gitea container ('gitea') on docker-runtime
#      $ make teardown-service svc=gitea on_vm=docker-runtime env=production
#   3. Converge gitea on runtime-control
#      $ make converge-gitea env=production
#   4. Converge nginx-edge — update upstream to runtime-control
#      $ make converge-nginx-edge env=production

# 2. Execute (updates files + runs converges)
make migrate-service svc=gitea to=runtime-control env=production

# 3. Review + commit
git diff
git add inventory/ && git commit -m "migrate gitea: docker-runtime → runtime-control"
git push origin main
```
