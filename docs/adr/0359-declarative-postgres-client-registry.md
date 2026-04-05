# ADR 0359: Declarative PostgreSQL Client Registry

- **Date**: 2026-04-05
- **Status**: Proposed
- **Deciders**: platform team
- **Concern**: data, platform

## Context

The platform runs 28+ service-specific PostgreSQL databases on `postgres-lv3` (10.10.10.50). Adding a new database consumer today requires manual, error-prone updates across at least four independent files:

1. A new `{service}_postgres` Ansible role — 70+ lines of copy-pasted boilerplate (password generation, user creation, database creation, owner assertion)
2. `inventory/group_vars/postgres_guests.yml` — add the source VM's IP to `postgres_vm_client_allowed_sources_extra`
3. `inventory/host_vars/proxmox_florin.yml` — add an `allowed_inbound` entry under `postgres-lv3` for the nftables guest firewall
4. Optionally `/etc/pve/firewall/150.fw` — add a Proxmox-level TAP firewall rule

This pattern violates DRY at every layer:

- **30 near-identical `{service}_postgres` roles** each independently implement password generation, user creation, database creation, and ownership correction.
- **`pg_hba.conf` allows all databases for all users from each allowed CIDR** — broad rather than least-privilege. A service whose IP is allowed can connect to any database.
- **`postgres_guests.yml` hard-codes only `docker_runtime` and `runtime_control` VMs** — any new consumer VM (e.g., `runtime-ai-lv3`, `coolify-lv3`) requires a code change to `postgres_guests.yml` rather than a data change.
- **No single inventory location** declares "which services consume postgres and from which VM." Operators must grep across three files to answer this question.
- **Stale state is the default**: the nftables in `proxmox_florin.yml` was discovered to be missing the `runtime-control-lv3` entry (ADR 0346 incident), requiring manual emergency hotfix on a live system.

## Decision

Introduce a **declarative PostgreSQL client registry** as the single source of truth for all service database relationships. All downstream artifacts — `pg_hba.conf`, nftables `allowed_inbound`, and the Proxmox VM firewall — are generated from this registry.

### Registry structure

Define `platform_postgres_clients` in `inventory/group_vars/platform.yml`:

```yaml
platform_postgres_clients:
  - service: gitea
    database: gitea
    user: gitea
    source_vm: docker-runtime-lv3
    password_local_file: "{{ platform_local_artifact_dir }}/postgres/gitea-password.txt"

  - service: keycloak
    database: keycloak
    user: keycloak
    source_vm: runtime-control-lv3
    password_local_file: "{{ platform_local_artifact_dir }}/postgres/keycloak-password.txt"

  - service: langfuse
    database: langfuse
    user: langfuse
    source_vm: runtime-control-lv3
    password_local_file: "{{ platform_local_artifact_dir }}/postgres/langfuse-password.txt"

  # ... one entry per service
```

Each entry is a data declaration, not a code change.

### Shared provisioning role: `postgres_client`

Replace the 30 near-identical `{service}_postgres` roles with a single shared role `postgres_client` that accepts the registry entry as its input:

```yaml
- name: Provision Gitea database
  ansible.builtin.include_role:
    name: lv3.platform.postgres_client
  vars:
    postgres_client_service: "{{ item.service }}"
    postgres_client_database: "{{ item.database }}"
    postgres_client_user: "{{ item.user }}"
    postgres_client_password_local_file: "{{ item.password_local_file }}"
  loop: "{{ platform_postgres_clients | selectattr('service', 'equalto', 'gitea') }}"
```

The `postgres_client` role handles: password file generation (idempotent), remote password mirroring to the control machine, PostgreSQL user creation (idempotent), database creation (idempotent), and ownership assertion.

Existing `{service}_postgres` roles become one-line wrappers calling `postgres_client` with their entry from `platform_postgres_clients`, or are removed entirely and their callers updated to use the shared role directly.

### pg_hba.conf: least-privilege per-service entries

Replace the current broad template that allows all databases from each CIDR:

```
# Before (broad):
host    all    all    10.10.10.92/32    scram-sha-256
```

With per-service entries generated from the registry:

```
# After (least-privilege):
host    gitea       gitea       10.10.10.20/32    scram-sha-256
host    keycloak    keycloak    10.10.10.92/32    scram-sha-256
host    langfuse    langfuse    10.10.10.92/32    scram-sha-256
```

The `pg_hba.conf.j2` template loops over `platform_postgres_clients`, resolving each `source_vm` name to its IP via `platform_guest_catalog`:

```jinja2
{% for client in platform_postgres_clients %}
host    {{ client.database }}    {{ client.user }}    {{ platform_guest_catalog.by_name[client.source_vm].ipv4 }}/32    scram-sha-256
{% endfor %}
```

Docker bridge CIDR blocks (`172.16.0.0/12`, `192.168.0.0/16`, `10.200.0.0/16`) are retained as fallback entries for containerised workloads that MASQUERADE to the host IP or run in ephemeral bridge networks.

### nftables allowed_inbound: derived from the registry

The `postgres-lv3` `allowed_inbound` block in `inventory/host_vars/proxmox_florin.yml` is replaced by a generated section. A Jinja2 filter or generator script reads `platform_postgres_clients`, groups entries by `source_vm`, and emits one `allowed_inbound` rule per unique source VM:

```yaml
# Generated — do not edit manually. Source: platform_postgres_clients.
- source: docker-runtime-lv3
  protocol: tcp
  ports: [5432]
  description: "PostgreSQL clients: gitea, flagsmith, directus, ..."
- source: runtime-control-lv3
  protocol: tcp
  ports: [5432]
  description: "PostgreSQL clients: keycloak, langfuse, label-studio, ..."
```

The generation runs as part of `make generate-platform-vars` (same pipeline as ADR 0344 / ADR 0346).

### Validation

`scripts/generate_platform_vars.py` gains a `--check-postgres-clients` mode that:
1. Verifies every `source_vm` in `platform_postgres_clients` exists in `platform_guest_catalog`
2. Verifies every declared `source_vm` has a corresponding `allowed_inbound` entry under `postgres-lv3` in `proxmox_florin.yml`
3. Warns if a `{service}_postgres` role exists that has no corresponding `platform_postgres_clients` entry (orphaned role)

This check runs in the `schema-validation` gate lane.

## Consequences

**Positive:**
- Adding a new service database requires one data change (one entry in `platform_postgres_clients`) rather than four code changes in separate files
- `pg_hba.conf` enforces least-privilege: a compromised docker-runtime-lv3 container cannot connect to the keycloak database
- The nftables `allowed_inbound` for `postgres-lv3` is always in sync with the declared clients — the incident that motivated ADR 0346 (missing nftables rule for runtime-control-lv3) cannot recur
- A single `postgres_client` role eliminates ~2000 lines of duplicate boilerplate across 30 roles
- `platform_postgres_clients` serves as live documentation: operators can see all database relationships in one place

**Negative / Trade-offs:**
- Migration work: all 30 existing `{service}_postgres` roles must be audited and either updated to call `postgres_client` or have their callers updated. This is a significant but mechanical refactor.
- `pg_hba.conf` least-privilege entries require that every active database client is declared in `platform_postgres_clients`. Any undeclared legacy connection will break on the next `postgres_vm` play run. A migration gate check is required before the cutover.
- The broad Docker bridge CIDR fallback entries (`172.16.0.0/12` etc.) remain for containerised workloads; fully eliminating them requires per-container static IP assignment (out of scope for this ADR).

## Implementation plan

1. Add `platform_postgres_clients` to `inventory/group_vars/platform.yml` with all current service entries (data migration, no behaviour change)
2. Add validation to `generate_platform_vars.py` and the schema-validation gate
3. Implement `postgres_client` shared role
4. Update `pg_hba.conf.j2` to generate per-service least-privilege entries
5. Add generator for `postgres-lv3` `allowed_inbound` block in `proxmox_florin.yml`
6. Migrate each existing `{service}_postgres` role to call `postgres_client` (can be done incrementally per-service)
7. Remove orphaned boilerplate from roles that have been migrated

## Depends on

- ADR 0026 (PostgreSQL VM Baseline) — foundational model
- ADR 0344 (Single-Source Environment Topology) — `platform_guest_catalog` for IP resolution
- ADR 0346 (Centralized Port Registry) — generator pipeline this ADR extends

## Related

- ADR 0098 (PostgreSQL HA) — replica and VIP topology unaffected
- ADR 0303 (pgaudit) — audit logging unaffected
- ADR 0304 (Atlas schema migrations) — schema versioning unaffected
