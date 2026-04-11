# ADR 0346: PostgreSQL Domain Clustering

- Status: Accepted
- Implementation Status: Not Started
- Implemented In Repo Version: 0.179.0
- Implemented On: —
- Date: 2026-04-04
- Tags: postgres, infrastructure, vm-separation, reliability, blast-radius

## Context

The platform currently runs a single PostgreSQL HA cluster serving all services:

```
  postgres          postgres-replica
  VMID 150              VMID 151
  10.10.10.50    <-->   10.10.10.51
        \               /
         VIP 10.10.10.55
         database.example.com
              |
    ALL ~20+ platform databases
```

Every service — from Keycloak authentication to Langfuse trace ingestion —
shares the same two VMs, the same connection pool, and the same I/O budget.

### Recurring problems

**I/O contention from analytics workloads.** Langfuse stores LLM traces,
Lago records billing events, and Plausible (currently using embedded PostgreSQL
inside Docker) writes page-view rows in high-throughput bulk-INSERT patterns.
These workloads saturate disk I/O during peak ingestion, which increases
query latency across every database on the cluster — including Keycloak.
Keycloak auth latency directly degrades every human login and every CI job
that triggers an OAuth token exchange.

**Cross-service migration locks.** A misbehaving schema migration from one
app (e.g., a long-running `ALTER TABLE` in Mattermost) acquires locks that
are visible to the PostgreSQL shared cache and connection queue, delaying
unrelated services.

**Shared connection pool exhaustion.** All services compete for the same
`max_connections` ceiling. A connection spike from one service (e.g.,
n8n workflow fan-out) reduces available connections for Gitea and Woodpecker.

**Unified backup/restore blast radius.** A point-in-time restore or vacuum
maintenance window that requires bringing the cluster read-only affects all
services simultaneously.

**WAL amplification.** Bulk analytic writes inflate WAL volume, increasing
replication lag on the replica and slowing checkpoint cycles for OLTP
services that share the primary.

### What does not change

Plausible currently runs an embedded PostgreSQL instance inside its Docker
Compose stack. This ADR moves it to the external `postgres-data` cluster,
giving it proper replication, backup coverage, and monitoring.

`changedetection` uses SQLite — no change needed.

## Decision

Split the single PostgreSQL cluster into three purpose-specific clusters,
each sized and tuned for its workload domain:

```
BEFORE
───────────────────────────────────────────────────────────────
  postgres + postgres-replica
  VIP: 10.10.10.55 / database.example.com
  ALL databases (keycloak, gitea, mattermost, langfuse, …)


AFTER
───────────────────────────────────────────────────────────────

  CLUSTER 1: postgres-control          (existing VMs, renamed role)
  ┌─────────────────────────────────────────────────────────┐
  │  postgres (VMID 150, 10.10.10.50)                  │
  │  postgres-replica (VMID 151, 10.10.10.51)          │
  │  VIP: 10.10.10.55 / database.example.com  (UNCHANGED)      │
  │                                                         │
  │  keycloak · gitea · windmill · windmill_admin           │
  │  woodpecker · temporal · temporal_visibility            │
  │  openfga · semaphore · vaultwarden · harbor · one_api   │
  └─────────────────────────────────────────────────────────┘

  CLUSTER 2: postgres-apps             (new VMs)
  ┌─────────────────────────────────────────────────────────┐
  │  postgres-apps (VMID 152, 10.10.10.52)             │
  │  postgres-apps-replica-lv3 (VMID 153, 10.10.10.53) *   │
  │  VIP: 10.10.10.56 / database-apps.example.com  (NEW)       │
  │                                                         │
  │  mattermost · matrix_synapse · mautrix_discord          │
  │  mautrix_whatsapp · nextcloud · outline · plane         │
  │  vikunja · n8n · netbox · directus · label_studio       │
  │  sftpgo · paperless                                     │
  └─────────────────────────────────────────────────────────┘

  CLUSTER 3: postgres-data             (new VMs)
  ┌─────────────────────────────────────────────────────────┐
  │  postgres-data (VMID 154, 10.10.10.54)             │
  │  postgres-data-replica-lv3 (VMID 155, 10.10.10.55?) *  │
  │  VIP: 10.10.10.57 / database-data.example.com  (NEW)       │
  │  NOTE: 10.10.10.55 is taken by control VIP; data        │
  │  replica uses .55 in the /24 but VIP is .57             │
  │                                                         │
  │  langfuse · flagsmith · lago · glitchtip · dify         │
  │  superset · grist · plausible (moved from embedded)     │
  │  paperless_ngx                                          │
  └─────────────────────────────────────────────────────────┘

  * replica VMs are provisioned in a follow-on step
```

### Cluster 1 — postgres-control (existing cluster)

**Purpose:** Identity, automation, and control-plane services. Auth latency
from this cluster is user-visible on every session start and every CI trigger.
It must remain isolated from analytic write storms.

**VMs (unchanged):**
- `postgres`, VMID 150, 10.10.10.50
- `postgres-replica`, VMID 151, 10.10.10.51

**VIP (unchanged):** 10.10.10.55 — `database.example.com`

**Database assignments:**

| Database | Service |
|---|---|
| `keycloak` | Keycloak SSO |
| `gitea` | Gitea source control |
| `windmill` | Windmill workflows |
| `windmill_admin` | Windmill admin DB |
| `woodpecker` | Woodpecker CI |
| `temporal` | Temporal workflow engine |
| `temporal_visibility` | Temporal visibility DB |
| `openfga` | OpenFGA authorization |
| `semaphore` | Semaphore task runner |
| `vaultwarden` | Vaultwarden password manager |
| `harbor` | Harbor container registry (if external DB enabled) |
| `one_api` | One API gateway |

**Tuning intent:** Low-latency OLTP. Favor `random_page_cost` reduction,
tight `work_mem` per connection, high `checkpoint_completion_target`.

### Cluster 2 — postgres-apps (new)

**Purpose:** Communication, collaboration, and productivity apps. These
services generate large blobs (Matrix media, Nextcloud file metadata,
Mattermost message history) and have bursty write patterns distinct from
control-plane OLTP. They can tolerate slightly higher replication lag
without impacting auth.

**VMs (new):**
- `postgres-apps`, VMID 152, 10.10.10.52 — primary (provision first)
- `postgres-apps-replica-lv3`, VMID 153, 10.10.10.53 — replica (follow-on)

**VIP:** 10.10.10.56 — `database-apps.example.com` (new DNS entry required)

**Spec:** 4 vCPU, 8 GB RAM, 128 GB disk (primary). Replica matches.

**Database assignments:**

| Database | Service |
|---|---|
| `mattermost` | Mattermost team chat |
| `matrix_synapse` | Matrix Synapse homeserver |
| `mautrix_discord` | Mautrix Discord bridge |
| `mautrix_whatsapp` | Mautrix WhatsApp bridge |
| `nextcloud` | Nextcloud file storage |
| `outline` | Outline knowledge base |
| `plane` | Plane project management |
| `vikunja` | Vikunja task manager |
| `n8n` | n8n automation workflows |
| `netbox` | Netbox IPAM/DCIM |
| `directus` | Directus headless CMS |
| `label_studio` | Label Studio ML annotation |
| `sftpgo` | SFTPGo file transfer |
| `paperless` | Paperless-ngx documents |

**Tuning intent:** Mixed OLTP/blob. Increase `effective_cache_size`,
allow higher `maintenance_work_mem` for vacuuming large attachment tables.

### Cluster 3 — postgres-data (new)

**Purpose:** Analytics, observability, and billing. These workloads issue
high-throughput bulk INSERTs (traces, metrics, events, page views) that
inflate WAL and saturate sequential I/O. Isolating them prevents monitoring
infrastructure from impairing user-facing services.

**VMs (new):**
- `postgres-data`, VMID 154, 10.10.10.54 — primary (provision first)
- `postgres-data-replica-lv3`, VMID 155, 10.10.10.55 — replica (follow-on;
  note: this VM IP 10.10.10.55 is within the /24 but the *VIP* for this
  cluster is 10.10.10.57 to avoid collision with the control VIP)

**VIP:** 10.10.10.57 — `database-data.example.com` (new DNS entry required)

**Spec:** 4 vCPU, 8 GB RAM, 128 GB disk (primary). Replica matches.

**Database assignments:**

| Database | Service | Notes |
|---|---|---|
| `langfuse` | Langfuse LLM observability | High trace INSERT rate |
| `flagsmith` | Flagsmith feature flags | — |
| `lago` | Lago billing engine | Billing event INSERTs |
| `glitchtip` | GlitchTip error tracking | — |
| `dify` | Dify AI platform | — |
| `superset` | Apache Superset BI | — |
| `grist` | Grist spreadsheet DB | — |
| `plausible` | Plausible analytics | Moved from embedded Docker PG |
| `paperless_ngx` | Paperless-ngx | Duplicate of `paperless` above if single DB used |

**Tuning intent:** Write-optimised. Raise `wal_buffers`,
`checkpoint_timeout`, `max_wal_size`. Set `synchronous_commit = off`
for analytics tables where loss of a few seconds of data is acceptable
(flagsmith, langfuse traces). Keep `synchronous_commit = on` for lago
billing events.

### Plausible migration note

Plausible currently embeds PostgreSQL as a container in its Docker Compose
stack (`plausible_db` service). After this ADR is implemented:

1. The embedded `plausible_db` container is removed from the Compose file.
2. The `plausible` database is created on `postgres-data`.
3. `DATABASE_URL` in the Plausible env points to `database-data.example.com`.
4. An initial `pg_dump` from the embedded container seeds the external DB.

## Places That Need to Change

### 1. `inventory/hosts.yml`

**What:** Add `postgres-apps` (VMID 152, 10.10.10.52) and
`postgres-data` (VMID 154, 10.10.10.54) to the `postgres_guests`
and `lv3_guests` inventory groups.

**Why:** Ansible targets these hosts for the `postgres_vm` role and for
common guest operations (cert renewal, observability, backup).

### 2. `inventory/host_vars/proxmox-host.yml`

**What:**
- Add VM definitions for VMID 152 (`postgres-apps`) and VMID 154
  (`postgres-data`) in the Proxmox VM spec block.
- Add Tailscale TCP proxy entries for the new postgres VMs so the
  controller can reach their postgres port (5432) through the mesh.

**Why:** The Proxmox host provisions VMs from this definition file. The
TCP proxy entries allow the `postgres_vm` Ansible role to configure users
and databases without a direct routed path.

### 3. `inventory/group_vars/platform.yml`

**What:**
- Add `postgres_apps_host: database-apps.example.com` and
  `postgres_data_host: database-data.example.com` as platform-wide variables.
- For each service migrating to the apps cluster, add or update a
  `postgres_host` host_var or group_var override to
  `database-apps.example.com`.
- For each service migrating to the data cluster, set `postgres_host` to
  `database-data.example.com`.

**Services that need `postgres_host` updated to `database-apps.example.com`:**

| Service variable file | Current `postgres_host` | New value |
|---|---|---|
| `host_vars/mattermost-lv3.yml` | `database.example.com` | `database-apps.example.com` |
| `host_vars/matrix-synapse-lv3.yml` | `database.example.com` | `database-apps.example.com` |
| `host_vars/nextcloud-lv3.yml` | `database.example.com` | `database-apps.example.com` |
| `host_vars/outline-lv3.yml` | `database.example.com` | `database-apps.example.com` |
| `host_vars/plane-lv3.yml` | `database.example.com` | `database-apps.example.com` |
| `host_vars/vikunja-lv3.yml` | `database.example.com` | `database-apps.example.com` |
| `host_vars/n8n-lv3.yml` | `database.example.com` | `database-apps.example.com` |
| `host_vars/netbox-lv3.yml` | `database.example.com` | `database-apps.example.com` |
| `host_vars/directus-lv3.yml` | `database.example.com` | `database-apps.example.com` |
| `host_vars/label-studio-lv3.yml` | `database.example.com` | `database-apps.example.com` |
| `host_vars/sftpgo-lv3.yml` | `database.example.com` | `database-apps.example.com` |
| `host_vars/paperless-lv3.yml` | `database.example.com` | `database-apps.example.com` |
| `host_vars/mautrix-discord-lv3.yml` | `database.example.com` | `database-apps.example.com` |
| `host_vars/mautrix-whatsapp-lv3.yml` | `database.example.com` | `database-apps.example.com` |

**Services that need `postgres_host` updated to `database-data.example.com`:**

| Service variable file | Current `postgres_host` | New value |
|---|---|---|
| `host_vars/langfuse-lv3.yml` | `database.example.com` | `database-data.example.com` |
| `host_vars/flagsmith-lv3.yml` | `database.example.com` | `database-data.example.com` |
| `host_vars/lago-lv3.yml` | `database.example.com` | `database-data.example.com` |
| `host_vars/glitchtip-lv3.yml` | `database.example.com` | `database-data.example.com` |
| `host_vars/dify-lv3.yml` | `database.example.com` | `database-data.example.com` |
| `host_vars/superset-lv3.yml` | `database.example.com` | `database-data.example.com` |
| `host_vars/grist-lv3.yml` | `database.example.com` | `database-data.example.com` |
| `host_vars/plausible-lv3.yml` | embedded Docker PG | `database-data.example.com` |

### 4. `collections/ansible_collections/lv3/platform/roles/postgres_vm/`

**What:**
- Verify that the role accepts a `postgres_vip` parameter so it can
  configure keepalived/Patroni with the correct VIP per cluster
  (10.10.10.55, .56, .57).
- Confirm the role's `defaults/main.yml` does not hard-code
  `10.10.10.55` or `database.example.com`; those must be passed as vars.
- Add `postgres_apps_vip: 10.10.10.56` and `postgres_data_vip: 10.10.10.57`
  as documented role variables.

**Why:** The existing role was written for a single cluster. Deploying
two additional clusters with the same role requires it to be fully
parameterised on IP and hostname.

### 5. `collections/ansible_collections/lv3/platform/playbooks/postgres-vm.yml`

**What:** Verify or extend the playbook to accept an `--extra-vars` parameter
(e.g., `cluster: apps`) that selects the right host group and variable set
when deploying `postgres-apps` vs `postgres-data`.

**Why:** Currently the playbook likely targets `postgres_guests` as a whole.
Adding two new VMs to that group means the playbook must be able to target a
single cluster during migration without affecting the running control cluster.

### 6. `collections/ansible_collections/lv3/platform/roles/plausible_runtime/`

**What:**
- Remove the embedded `plausible_db` PostgreSQL container from
  `templates/docker-compose.yml.j2`.
- Update `templates/runtime.env.j2` and `templates/runtime.env.ctmpl.j2`
  to set `DATABASE_URL` to the external postgres-data endpoint.
- Add `postgres_host` and `postgres_db` to `defaults/main.yml` and
  `meta/argument_specs.yml`.

**Why:** Plausible is the only service using embedded PostgreSQL. Moving it
to the external cluster gives it proper replication and backup coverage.

### 7. DNS entries (internal)

**What:** Add two internal DNS A records:
- `database-apps.example.com` → `10.10.10.56`
- `database-data.example.com` → `10.10.10.57`

**Why:** All service `postgres_host` vars use hostnames. The VIP IP may
change if topology changes; hostnames decouple services from IP addresses.

### 8. Monitoring and alerting

**What:** Extend the existing postgres monitoring stack to cover the two new
clusters:
- Add postgres exporter scrape targets for `10.10.10.52` and `10.10.10.54`.
- Update Grafana postgres dashboards to include a cluster selector variable.
- Add alerting rules for replication lag on the new clusters.

**Why:** Three clusters means three independent replication lag metrics.
The existing single-cluster alert rules only fire for `10.10.10.50`.

## Consequences

### Positive

- **Auth latency isolation.** Keycloak, Gitea, and Woodpecker are fully
  isolated from analytics I/O. Heavy Langfuse or Plausible ingestion
  no longer causes PostgreSQL lock wait time-outs on the control plane.

- **Independent scaling.** Each cluster can be sized to its workload.
  The data cluster can get larger disks and be tuned for write throughput.
  The apps cluster can get more RAM for large blob caching. The control
  cluster stays lean and fast.

- **Independent maintenance windows.** Vacuuming, REINDEX, or
  point-in-time restore on the data cluster does not affect services on
  the control or apps clusters.

- **Blast radius reduction.** A misconfigured migration, connection pool
  exhaustion, or disk-full event on one cluster cannot cascade to services
  on a different cluster. This is the same principle as ADR 0340 applied
  to the database tier.

- **WAL isolation.** High-volume INSERTs on the data cluster no longer
  inflate WAL checkpoints for the control cluster.

### Negative / Trade-offs

- **Operational complexity increases.** Three clusters to monitor, back
  up, patch, and failover. Each cluster requires its own keepalived/Patroni
  configuration, its own backup schedule, and its own replication monitoring.

- **IP address space consumed.** VMIDs 152–155 and IPs 10.10.10.52–10.10.10.57
  are reserved. This is a small but non-zero allocation from the /24.

- **Migration risk.** Each database must be dumped from the control cluster
  and restored to the appropriate new cluster during a maintenance window.
  Services must be quiesced during their individual migration step to prevent
  split-write data loss.

- **New DNS names.** Services currently hard-coding `database.example.com` in
  env vars or secrets (e.g., stored in OpenBao) must have those values
  updated when the service migrates. Missed entries will cause connection
  failures.

- **Replica lag divergence.** Previously a single replication status covered
  all databases. Now three independent replication health signals must be
  tracked. An undetected lag on the data cluster's replica means analytics
  data is less protected than expected.

## Implementation Order

The migration is performed cluster-by-cluster. The control cluster is not
touched until apps and data clusters are confirmed stable. Each service
migration is atomic: dump, restore, update vars, restart service, verify.

### Phase 1 — Provision postgres-apps cluster

1. Allocate VMID 152 and IP 10.10.10.52 in `inventory/host_vars/proxmox-host.yml`.
2. Add `postgres-apps` to `inventory/hosts.yml` under `postgres_guests`.
3. Add DNS A record: `database-apps.example.com` → `10.10.10.56`.
4. Provision the VM via Proxmox (4 vCPU, 8 GB RAM, 128 GB disk).
5. Run `postgres-vm.yml` targeting `postgres-apps` to install and
   configure PostgreSQL with VIP 10.10.10.56.
6. Verify PostgreSQL is reachable at `database-apps.example.com:5432`.

### Phase 2 — Migrate apps-cluster databases

For each service in the apps cluster assignment table:

1. Quiesce the service (scale Docker Compose service to 0 replicas or
   enable maintenance mode).
2. `pg_dump -h database.example.com -U <user> <db> | psql -h database-apps.example.com -U <user> <db>`
3. Update `postgres_host` in the service's inventory var file to
   `database-apps.example.com`.
4. Re-run the service playbook to regenerate env files and restart.
5. Smoke-test the service (health check, login, representative write).
6. After all apps services are verified, drop migrated databases from
   `postgres` (do not drop until all services on the apps cluster
   are confirmed stable for at least 24 hours).

### Phase 3 — Provision postgres-data cluster

1. Allocate VMID 154 and IP 10.10.10.54 in `inventory/host_vars/proxmox-host.yml`.
2. Add `postgres-data` to `inventory/hosts.yml` under `postgres_guests`.
3. Add DNS A record: `database-data.example.com` → `10.10.10.57`.
4. Provision the VM (4 vCPU, 8 GB RAM, 128 GB disk).
5. Run `postgres-vm.yml` targeting `postgres-data` with VIP 10.10.10.57.
6. Verify PostgreSQL is reachable at `database-data.example.com:5432`.

### Phase 4 — Migrate data-cluster databases

Same per-service procedure as Phase 2. Additional step for Plausible:

1. Stop Plausible Docker Compose stack.
2. Dump embedded DB: `docker exec plausible_db pg_dump -U postgres plausible`
3. Restore to external: `psql -h database-data.example.com -U plausible plausible`
4. Update `plausible_runtime` role to remove embedded DB container and
   set `DATABASE_URL` to external endpoint.
5. Redeploy Plausible.
6. Verify analytics are recording correctly.

### Phase 5 — Replica provisioning (follow-on, not blocking Phase 1–4)

7. Provision `postgres-apps-replica-lv3` (VMID 153, 10.10.10.53) and
   configure streaming replication from `postgres-apps`.
8. Provision `postgres-data-replica-lv3` (VMID 155, 10.10.10.55) and
   configure streaming replication from `postgres-data`.
9. Add VIP failover configuration (keepalived) for both new clusters.
10. Extend monitoring: add postgres exporter targets, update Grafana dashboards,
    add replication lag alerts for each new cluster.

### Phase 6 — Control cluster clean-up

11. After all migrated databases have been stable on their new clusters
    for a minimum of 48 hours, drop the migrated databases from `postgres`.
12. Reclaim disk space with `VACUUM FULL` on `postgres` (schedule a
    maintenance window; this requires brief write unavailability).

## Related ADRs

- ADR 0340: Dedicated Coolify Apps VM Separation — same blast-radius
  isolation pattern applied to the VM tier
- ADR 0341: Open-WebUI Keycloak OIDC with Break-Glass Fallback — depends
  on control-cluster Keycloak reliability
- ADR 0342: Zero-SSH Guest Operations via Proxmox QAPI — migration steps
  use the guest-exec primitive to run pg_dump/psql inside VMs
- ADR 0344: Single-Source Environment Topology — new VMs must be added
  to the topology snapshot so operator tools can discover them
- ADR 0347: docker-runtime Workload Split (related separation concern)
