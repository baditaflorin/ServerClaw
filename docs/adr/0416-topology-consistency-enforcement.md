# ADR 0416: Topology Consistency Enforcement

**Date:** 2026-04-14
**Status:** Implemented
**Related:** ADR 0359 (Declarative PostgreSQL Registry), ADR 0373 (Service Registry and Derived Defaults), ADR 0374 (Cross-Cutting Service Manifest), ADR 0407 (Generic-by-Default with Local Overlay), ADR 0410 (Docker Isolation Testing and IoC Completion), ADR 0413 (SSO Redirect URI Mismatch and Service Topology Variable Drift)

---

## Context

### The Incident (2026-04-14)

A user reported `chat.example.com` returning "An internal server error has occurred" during
Keycloak SSO login. Investigation revealed:

```
2026-04-13 21:32:23,707 ERROR [org.keycloak.services.error.KeycloakErrorHandler]
Uncaught server error: Unable to acquire JDBC Connection
FATAL: no pg_hba.conf entry for host "10.10.10.92", user "keycloak", database "keycloak"
```

**Root cause:** Keycloak had been migrated from `docker-runtime` (10.10.10.20) to
`runtime-control` (10.10.10.92) in a previous session. Three registries encode the
service-to-VM assignment, and only two of them were updated:

| Registry | Field | Expected | Actual |
|----------|-------|----------|--------|
| `inventory/host_vars/proxmox-host.yml` | `lv3_service_topology.keycloak.owning_vm` | `runtime-control` | `runtime-control` ✓ |
| `inventory/group_vars/platform.yml` (generated) | `keycloak_upstream.host` | `runtime-control` | `runtime-control` ✓ |
| `inventory/group_vars/platform_postgres.yml` | `platform_postgres_clients[keycloak].source_vm` | `runtime-control` | `docker-runtime` ✗ |
| `inventory/group_vars/all/platform_services.yml` | `platform_service_registry.keycloak.host_group` | `runtime-control` | `docker-runtime` ✗ |

Because `platform_postgres.yml` still had `source_vm: docker-runtime`, the PostgreSQL
`pg_hba.conf` template only allowed connections from 10.10.10.20. Keycloak on
10.10.10.92 was blocked at the database layer on every request.

### Why This Keeps Happening

This is the **third** topology drift incident in 72 hours:

| Date | Incident | Drifted registries |
|------|----------|--------------------|
| 2026-04-13 | nginx edge reverting sso.example.com to docker-runtime | `lv3_service_topology`, `platform.yml` |
| 2026-04-13 | SSO redirect URI mismatch (ADR 0413) | collection role, standalone role, tests |
| 2026-04-14 | Keycloak pg_hba.conf blocking runtime-control | `platform_postgres_clients`, `platform_service_registry` |

The platform encodes "which VM runs this service" in **four independent places**:

1. `inventory/group_vars/all/platform_services.yml` → `host_group` (Ansible deployment target)
2. `inventory/host_vars/proxmox-host.yml` → `lv3_service_topology[s].owning_vm` (nginx routing)
3. `inventory/group_vars/platform_postgres.yml` → `platform_postgres_clients[s].source_vm` (pg_hba.conf)
4. `inventory/group_vars/platform.yml` (generated) → `keycloak_upstream`, etc.

There is no automated check that these four stay in sync. A human can update one and
forget the others. The platform has no pre-push guard for this class of error.

### What ADR 0373/0374 Already Addressed

ADR 0373 created `platform_service_registry` as the single source of truth for service
identity. ADR 0374 extended it with DNS, proxy, TLS, SSO, and hairpin declarations.
ADR 0413 fixed a related drift (service topology variable references in role defaults).

What none of these ADRs addressed: the cross-registry consistency check between
`platform_service_registry.host_group`, `platform_postgres_clients.source_vm`, and
`lv3_service_topology.owning_vm`.

---

## Decision

### 1. Establish the authority hierarchy for VM assignment

```
platform_service_registry.host_group   ← AUTHORITATIVE (single source of truth)
         │
         ├─ platform_postgres_clients.source_vm    MUST match
         └─ lv3_service_topology.owning_vm         MUST match (where it exists)
```

When any of these disagree, `platform_service_registry.host_group` wins.
Operators must update the others to match it.

### 2. Implement a cross-registry topology consistency validator

**Script:** `scripts/validate_topology_consistency.py`

Three checks:
- **Check A** — Every `platform_postgres_clients[s].source_vm` matches
  `platform_service_registry[s].host_group` (where the service appears in both)
- **Check B** — Every `lv3_service_topology[s].owning_vm` matches
  `platform_service_registry[s].host_group` (where the service appears in both)
- **Check C** — Every `source_vm` value references a valid inventory hostname

Usage:
```bash
# Validate (exit 1 on drift):
python scripts/validate_topology_consistency.py --check

# Print full consistency table:
python scripts/validate_topology_consistency.py --list

# Print drift details without writing:
python scripts/validate_topology_consistency.py --fix-dry-run
```

### 3. Add the validator to the pre-push gate

The validator runs in the `schema-validation` gate lane alongside
`validate_service_registry.py`. A push to main is rejected if any topology
consistency drift is detected.

Gate addition (in `.git/hooks/pre-push`):
```bash
echo "validation gate: validating topology consistency (ADR 0416)"
uv run --with pyyaml python scripts/validate_topology_consistency.py --check
```

### 4. Operator procedure when moving a service to a different VM

**⚠ This manual procedure is superseded by ADR 0417. Use `make migrate-service`.**

```bash
# Preview what will change (no files touched, no converges run):
make migrate-service-dry-run svc=<svc> to=<new-vm>

# Execute: updates all three registry files + runs ordered converges + writes receipt:
make migrate-service svc=<svc> to=<new-vm> env=production

# Then commit the registry changes:
git diff && git add inventory/ && git commit -m "migrate <svc>: <old-vm> → <new-vm>"
git push origin main
```

`make migrate-service` updates `host_group`, `proxy.upstream_host`, and
`lv3_service_topology.owning_vm` atomically, runs topology validation, then
converges in the correct order (postgres → stop-old → service → nginx).

The manual 5-step procedure below is kept for reference only. Do not use it
for new migrations — it is error-prone and bypasses the receipt system.

<details>
<summary>Legacy manual procedure (reference only — use make migrate-service instead)</summary>

```yaml
# Step 1: Update the authoritative registry
# inventory/group_vars/all/platform_services.yml
  <svc>:
    host_group: <new-vm>    # was: <old-vm>

# Step 2: Update nginx routing topology (if the service has a public endpoint)
# inventory/host_vars/proxmox-host.yml
  lv3_service_topology:
    <svc>:
      owning_vm: <new-vm>   # was: <old-vm>
      upstream: "http://{{ ... <new-vm> ... }}:..."

# Step 3: Verify consistency
python scripts/validate_topology_consistency.py --check

# Step 4: Converge affected services (order matters!)
make converge-postgres-vm env=production        # updates pg_hba.conf
make teardown-service svc=<svc> on_vm=<old-vm> # stop old container
make converge-<svc> env=production              # start on new VM
make converge-nginx-edge env=production         # updates nginx upstream
```
</details>

### 5. Phase 2 COMPLETE: derive source_vm from host_group automatically ✅

**Implemented 2026-04-14** — `source_vm` has been eliminated from all 27
`platform_postgres_clients` entries. The `pg_hba.conf.j2` template now derives
the client IP from `platform_service_registry[service].host_group`:

```yaml
# pg_hba.conf.j2 — ADR 0416 Phase 2 (implemented)
{% for client in platform_postgres_clients %}
{% if client.source_vm is defined %}
{# Legacy fallback — emits LEGACY warning comment, should not occur in clean state #}
{% set client_ip = platform_guest_catalog.by_name[client.source_vm].ipv4 + '/32' %}
host  {{ client.database }}  {{ client.user }}  {{ client_ip }}  scram-sha-256  # LEGACY
{% else %}
{% set host_group = platform_service_registry[client.service].host_group %}
{% set client_ip = platform_guest_catalog.by_name[host_group].ipv4 + '/32' %}
host  {{ client.database }}  {{ client.user }}  {{ client_ip }}  scram-sha-256
{% endif %}
{% endfor %}
```

The validator now checks for Phase 2 compliance — any entry with a `source_vm`
field is flagged as `LEGACY` and fails the gate. This makes drift impossible by
construction: moving a service's `host_group` automatically updates pg_hba.conf
on next converge with zero other changes required.

---

## Findings From the 2026-04-14 Audit

Running `validate_topology_consistency.py --list` immediately after implementing
this ADR revealed **20 topology drifts** across the platform. 14 were resolved
in this session by updating `platform_service_registry.host_group`:

| Service | Change | Evidence |
|---------|--------|----------|
| keycloak | docker-runtime → runtime-control | postgres source_vm + topology both agree |
| gitea | docker-runtime → runtime-control | postgres source_vm + topology both agree |
| openfga | docker-runtime → runtime-control | postgres source_vm + topology both agree |
| temporal | docker-runtime → runtime-control | postgres source_vm + topology both agree |
| vaultwarden | docker-runtime → runtime-control | postgres source_vm + topology both agree |
| windmill | docker-runtime → runtime-control | postgres source_vm + topology both agree |
| openbao | docker-runtime → runtime-control | topology owning_vm confirms |

### Remaining Drifts — RESOLVED (2026-04-14) ✅

All 6 items were SSH-verified the same day (2026-04-14) by running `docker ps` on
all candidate VMs. In every case the **topology was correct** and the **registry was wrong**.

| Service | Registry (wrong) | Topology (correct) | SSH Evidence | Corrected to |
|---------|-----------------|-------------------|--------------|--------------|
| `uptime_kuma` | docker-runtime | runtime-general | `docker ps` on runtime-general shows `uptime-kuma` | runtime-general |
| `mail_platform` | docker-runtime | runtime-control | `lv3-mail-stalwart` on runtime-control (+ orphaned copy on docker-runtime) | runtime-control |
| `redpanda` | runtime-control | docker-runtime | `lv3-redpanda` on docker-runtime, not on runtime-control | docker-runtime |
| `gotenberg` | docker-runtime | runtime-ai | `gotenberg` on runtime-ai, not on docker-runtime | runtime-ai |
| `ollama` | runtime-ai | docker-runtime | `ollama` on docker-runtime, runtime-ai has only tesseract/tika | docker-runtime |
| `piper` | runtime-ai | docker-runtime | `piper` on docker-runtime, not on runtime-ai | docker-runtime |

**Finding:** `lv3_service_topology` (proxmox-host.yml) stays accurate because nginx
breaks immediately if it's wrong. `platform_service_registry.host_group` accumulated
drift silently because it had no operational consequence enforcement. The gate check
closes this gap permanently.

**Note — `mail_platform` orphaned containers:** `lv3-mail-gateway` and `lv3-mail-stalwart`
were found running on BOTH runtime-control and docker-runtime. The docker-runtime copies
are orphaned. Clean up with:
```bash
ssh -J ops@10.10.10.1 ops@10.10.10.20 \
  "docker stop lv3-mail-gateway lv3-mail-stalwart && docker rm lv3-mail-gateway lv3-mail-stalwart"
```

---

## Consequences

### Positive

- Topology drift is caught at `git push` time, not at incident time
- `platform_service_registry.host_group` is now the declared single source of truth
  for service VM assignment, with a machine-enforced invariant
- The 14 registry entries that were stale are now corrected
- Human runbook for VM migrations is documented once (above) and discoverable
- The long-term path to eliminating `source_vm` entirely is documented

### Negative

- The pre-push gate now has one more check; pushes will be slower by a few seconds
- The validator can only check services that appear in ALL relevant registries;
  services that only appear in some registries (e.g., only topology, not registry)
  generate NOTICE-level output, not errors
- The 6 remaining drift items require SSH investigation; they are not auto-resolved

### Neutral

- `platform_postgres_clients.source_vm` is redundant with `platform_service_registry.host_group`
  and should be eliminated in Phase 2 (no timeline set)
- The validator uses a static exclude list (`TOPOLOGY_OWNING_VM_EXCLUDES`) for
  meta-entries like `docker_runtime`; this list should be reviewed when new
  system-level topology entries are added

---

## Files Changed

### Initial commit (2026-04-14 morning)
| File | Change |
|------|--------|
| `scripts/validate_topology_consistency.py` | New — ADR 0416 cross-registry consistency validator |
| `inventory/group_vars/all/platform_services.yml` | Updated `host_group` for 7 migrated services (keycloak, gitea, openfga, temporal, vaultwarden, windmill, openbao) |
| `inventory/group_vars/platform_postgres.yml` | Updated `source_vm` for keycloak (runtime-control) |
| `.git/hooks/pre-push` | Added topology consistency check to gate |
| `docs/postmortems/2026-04-14-keycloak-postgres-source-vm-drift.md` | Incident postmortem |

### Phase 2 commit (2026-04-14 afternoon — same day)
| File | Change |
|------|--------|
| `inventory/group_vars/all/platform_services.yml` | Corrected `host_group` for 6 more services (uptime_kuma, mail_platform, redpanda, gotenberg, ollama, piper) via SSH verification |
| `inventory/group_vars/platform_postgres.yml` | **Removed `source_vm` from all 27 entries** — field eliminated |
| `collections/.../postgres_vm/templates/pg_hba.conf.j2` | Derive client IP from `platform_service_registry[service].host_group`; legacy `source_vm` fallback with LEGACY comment |
| `scripts/validate_topology_consistency.py` | Updated postgres check: flag legacy `source_vm` fields; verify all services resolvable via registry |
| `docs/postmortems/2026-04-14-topology-audit-phase2-completion.md` | Phase 2 postmortem |
