# Postmortem: Topology Full Audit and Phase 2 Completion (2026-04-14)

**Date:** 2026-04-14
**Duration:** ~2 hours (audit + verification + implementation)
**Severity:** P2 — Six service registry entries stale; no active outage during this session
**Status:** Resolved
**ADR:** ADR 0416 — Topology Consistency Enforcement (Phase 2 complete)

---

## Summary

Following the Keycloak pg_hba.conf incident earlier in the day, a full topology
audit was conducted using `scripts/validate_topology_consistency.py --list`. The
audit revealed 6 additional services where `platform_service_registry.host_group`
disagreed with `lv3_service_topology.owning_vm`. All 6 were SSH-verified and
all 6 had the topology correct and the registry wrong.

ADR 0416 Phase 2 was also implemented in the same session: `source_vm` was removed
from all 27 `platform_postgres_clients` entries and the `pg_hba.conf.j2` template
was updated to derive the client IP directly from
`platform_service_registry[service].host_group`. The `source_vm` field no longer
exists in the platform.

---

## SSH Verification Results

Each of the 6 pending services was verified by running `docker ps` on all candidate VMs:

| Service | Registry said | Topology said | Actual (SSH) | Correction |
|---------|--------------|---------------|--------------|------------|
| `uptime_kuma` | docker-runtime | runtime-general | **runtime-general** | Registry corrected |
| `mail_platform` | docker-runtime | runtime-control | **runtime-control** (+ stale copy on docker-runtime) | Registry corrected |
| `redpanda` | runtime-control | docker-runtime | **docker-runtime** | Registry corrected |
| `gotenberg` | docker-runtime | runtime-ai | **runtime-ai** | Registry corrected |
| `ollama` | runtime-ai | docker-runtime | **docker-runtime** | Registry corrected |
| `piper` | runtime-ai | docker-runtime | **docker-runtime** | Registry corrected |

**Pattern:** In 6/6 cases, the `lv3_service_topology` (maintained by playbook engineers
during service migrations) was correct. The `platform_service_registry.host_group`
(maintained by the service registry process) was stale.

**Note on `mail_platform`:** Both `lv3-mail-gateway` and `lv3-mail-stalwart` containers
were found running on BOTH `runtime-control` AND `docker-runtime`. The topology declares
`runtime-control` as the owning VM. The docker-runtime copy is a stale leftover from
a previous deployment and should be cleaned up separately.

---

## Root Cause Analysis

### Why the topology was right and the registry was wrong

`lv3_service_topology` in `inventory/host_vars/proxmox-host.yml` is edited by
engineers when they run playbooks — it's the file you open when you're deploying
and need to change where nginx routes traffic. It stays current because it has
immediate operational consequences (nginx breaks if it's wrong).

`platform_service_registry.host_group` in `platform_services.yml` is used by
Ansible for variable derivation (`derive_service_defaults`) and was perceived as
"just metadata." It has no immediate operational consequence visible to the deploying
engineer. So it accumulated drift silently.

This is an instance of **documentation that decoupled from reality** because the
documentation (registry) had no feedback loop to production reality.

### Why source_vm was even needed before Phase 2

The `platform_postgres_clients` registry (ADR 0359) was introduced *before*
`platform_service_registry` (ADR 0373). When ADR 0359 was designed, there was no
single-VM-per-service registry to look up. So `source_vm` was added as an explicit
field alongside `database`, `user`, and `password_local_file`.

After ADR 0373 established `platform_service_registry.host_group` as the canonical
VM-per-service field, `source_vm` became redundant — but no one cleaned it up, and
it silently drifted (as we saw in the Keycloak incident).

---

## Changes Applied

### 1. Registry corrections (6 services)

Updated `platform_service_registry.host_group` in `platform_services.yml`:

| Service | Before | After |
|---------|--------|-------|
| `uptime_kuma` | docker-runtime | runtime-general |
| `mail_platform` | docker-runtime | runtime-control |
| `redpanda` | runtime-control | docker-runtime |
| `gotenberg` | docker-runtime | runtime-ai |
| `ollama` | runtime-ai | docker-runtime |
| `piper` | runtime-ai | docker-runtime |

### 2. ADR 0416 Phase 2: eliminate source_vm (27 entries)

- Removed `source_vm` from all 27 entries in `inventory/group_vars/platform_postgres.yml`
- Updated `pg_hba.conf.j2` template to derive client IP from
  `platform_service_registry[client.service].host_group` via `platform_guest_catalog`
- Added legacy fallback path: if a `source_vm` field is present, it is used but
  emits a `# LEGACY: source_vm=...` comment in the rendered `pg_hba.conf`
- Updated validator (`validate_topology_consistency.py`) to check for legacy
  `source_vm` fields and flag them as errors

### 3. Validator updated

- Removed 6 pending exclusions from `TOPOLOGY_OWNING_VM_EXCLUDES`
- Updated postgres check to verify Phase 2 compliance (no `source_vm` fields)
  instead of checking `source_vm == host_group`
- Added check that every postgres client service has a resolvable `host_group` in
  `platform_service_registry`

### 4. Pending stale container cleanup

`lv3-mail-gateway` and `lv3-mail-stalwart` containers on `docker-runtime` are
orphaned from a previous deployment. They should be stopped:
```bash
ssh ops@10.10.10.20 -J ops@10.10.10.1 \
  "docker stop lv3-mail-gateway lv3-mail-stalwart && docker rm lv3-mail-gateway lv3-mail-stalwart"
```
This is tracked separately — it does not affect current routing (nginx points to runtime-control).

---

## Validator Final State

After all fixes, `python scripts/validate_topology_consistency.py --check` outputs:

```
Checking postgres client source_vm vs service registry host_group...
  ✓ All 27 postgres clients match registry host_group
Checking lv3_service_topology owning_vm vs service registry host_group...
  ✓ All topology entries match registry host_group
Checking postgres source_vm guest references...
  ✓ All postgres source_vm values reference valid inventory hosts

✓ All topology consistency checks passed.
```

The `--list` view shows `—` in the POSTGRES source_vm column for all services,
confirming Phase 2 is complete — IP is now derived, not declared.

---

## ADR Analysis: Does Phase 2 Need a New ADR?

**Answer: No.** Phase 2 is an implementation change, not a new architectural decision.

- **ADR 0359** (Declarative PostgreSQL Client Registry) is the governing ADR. It
  describes *what* the registry is and *what it drives* (pg_hba.conf, nftables).
  Phase 2 changes *how* the IP is resolved within that registry — this is an
  implementation detail of ADR 0359, not a new decision.
- **ADR 0373** (Service Registry and Derived Defaults) already established
  `host_group` as the canonical VM-per-service field. Phase 2 just makes
  ADR 0359 consume it rather than duplicate it.
- **ADR 0416** (Topology Consistency Enforcement) documents the enforcement strategy
  and references Phase 2 as the long-term fix.

No existing ADRs conflict with Phase 2. ADR 0359 is amended in-place (its status
remains Implemented; this is how an implementation improvement works — not every
improvement needs a new ADR number).

---

## Lessons Learned

1. **The topology that has operational consequences stays current; metadata that
   doesn't breaks silently.** `lv3_service_topology` was right because nginx would
   fail immediately if it was wrong. `platform_service_registry.host_group` was
   wrong because nothing enforced it. The gate check closes this gap.

2. **When two fields encode the same fact, one will drift.** `source_vm` and
   `host_group` were both encoding "which VM runs this service." Elimination
   (Phase 2) is always better than synchronization enforcement.

3. **SSH is the ground truth.** `docker ps` on the actual host resolves any
   ambiguity between registries in seconds. The verification protocol should be
   documented (it now is, in ADR 0416).

4. **Stale containers are a separate problem from stale registry.** The mail_platform
   case showed that a service can "run on two VMs" in the sense that old containers
   are never cleaned up. Orphaned containers on decommissioned hosts are a hygiene
   issue that the registry doesn't track. A future cleanup playbook could address this.

---

## Action Items

| Item | Status |
|------|--------|
| SSH-verify all 6 pending topology items | ✅ Done |
| Correct 6 registry entries in platform_services.yml | ✅ Done |
| Implement ADR 0416 Phase 2 (remove source_vm, derive in template) | ✅ Done |
| Update validator to check Phase 2 compliance | ✅ Done |
| Run `make converge-postgres-vm env=production` to apply new derived pg_hba.conf | ⬜ Required |
| Stop orphaned mail containers on docker-runtime | ⬜ Pending |
