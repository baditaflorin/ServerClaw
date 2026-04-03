# ADR 0347: Docker Runtime Workload Split

- Status: Accepted
- Implementation Status: Not Started
- Implemented In Repo Version: 0.179.0
- Implemented On: —
- Date: 2026-04-04
- Tags: infrastructure, vm-separation, reliability, blast-radius, docker, runtime

## Context

`docker-runtime-lv3` (VMID 120, `10.10.10.20`, 4 vCPU, 24 GB RAM, 160 GB disk)
currently runs approximately 80 services covering everything from real-time
communications (Mattermost, Matrix-Synapse, LiveKit, Redpanda) to collaborative
productivity tools (Nextcloud, Outline, Woodpecker CI) to analytics and
observability (Langfuse, Plausible, Superset, Glitchtip).

Three VM separations have already been carved out from this VM:

| VM | VMID | IP | Workload |
|---|---|---|---|
| `runtime-ai-lv3` | 190 | 10.10.10.90 | AI/ML inference (Ollama, Piper) |
| `runtime-general-lv3` | 191 | 10.10.10.91 | Uptime Kuma, Homepage, Mailpit |
| `runtime-control-lv3` | 192 | 10.10.10.92 | Keycloak, OpenBao, Step-CA, Gitea, Harbor, Windmill, API Gateway, Mail Platform |

Despite those separations, `docker-runtime-lv3` retains roughly 80 services and
continues to exhibit the following recurring problems:

### Problem 1: I/O and CPU competition between fundamentally different workload classes

Redpanda (Kafka-compatible broker) performs continuous sequential I/O to write
partition logs. LiveKit (WebRTC) sustains kernel-level network processing for
video/audio streams. Both impose latency tails on co-located HTTP services
(Nextcloud file sync, Langfuse query dashboards) that expect sub-100 ms response
times. Resource cgroups cannot fully isolate these patterns within a single
Docker daemon.

### Problem 2: Blast radius — Docker daemon restart takes down 80 services

When the Docker daemon on `docker-runtime-lv3` must be restarted — for example
due to `iptables`/`nftables` nat chain corruption (observed in the incident
that motivated ADR 0329) — all 80 services stop simultaneously. Operators must
choose between leaving the platform partially broken (nat chain issue causes
broken container networking) or accepting a broad service outage to fix it.

### Problem 3: Woodpecker CI build spikes contaminate the entire VM

CI builds are bursty by nature: a pushed commit saturates all 4 vCPU cores for
30–90 seconds. Every other service on the VM experiences elevated P99 latency
during that window. CPU pinning is not possible across Docker Compose services
without invasive cgroup configuration.

### Problem 4: Disk I/O contention between message storage and object storage

Mattermost and Matrix-Synapse accumulate large attachment stores over time.
MinIO (S3-compatible object storage) handles bulk uploads from Nextcloud and
Directus. Woodpecker CI writes build artifact layers to the Docker daemon's
overlay2 storage. These three write patterns compete for the same disk queue
on a single VM.

### Problem 5: Resource limit tuning is mutually exclusive

Setting `mem_limit` for Nextcloud high enough for large file operations means
less headroom for Langfuse during a query burst. Tuning Redpanda's JVM heap
large reduces available memory for all other services. With 80 services sharing
24 GB, every limit is a trade-off with every other service.

### Current topology (before this ADR)

```
docker-runtime-lv3 (VMID 120, 10.10.10.20)
4 vCPU / 24 GB RAM / 160 GB disk
│
├── Communications (real-time, persistent connections)
│   ├── Mattermost          (ChatOps, message attachments)
│   ├── Matrix-Synapse      (federated IM)
│   ├── mautrix-discord     (bridge)
│   ├── mautrix-whatsapp    (bridge)
│   ├── LiveKit             (WebRTC video/audio)
│   └── Redpanda            (Kafka broker, I/O intensive)
│
├── Apps (collaborative productivity + CI/CD)
│   ├── Nextcloud           (file sync/share, heavy I/O)
│   ├── MinIO               (object storage)
│   ├── Outline             (team wiki)
│   ├── Plane               (project management)
│   ├── Vikunja             (task management)
│   ├── N8N                 (workflow automation)
│   ├── NetBox              (IPAM/DCIM)
│   ├── Directus            (CMS/API)
│   ├── Label Studio        (ML annotation)
│   ├── Paperless           (document management)
│   ├── Gotenberg           (PDF generation)
│   ├── Tika                (content extraction)
│   ├── Browser-Runner      (headless browser)
│   ├── Searxng             (meta search)
│   ├── Excalidraw          (collaborative drawing)
│   ├── ChangeDetection     (website monitor)
│   ├── Woodpecker CI       (CI/CD — CPU spike source)
│   ├── Portainer           (Docker management UI)
│   └── Dozzle              (Docker log viewer)
│
└── Data / Analytics / Observability
    ├── Langfuse            (LLM observability)
    ├── Flagsmith           (feature flags)
    ├── Plausible           (analytics)
    ├── Lago                (billing)
    ├── Glitchtip           (error tracking)
    ├── Dify                (LLM orchestration)
    ├── Superset            (BI)
    ├── Grist               (spreadsheets)
    ├── Typesense           (search engine)
    ├── One-API             (OpenAI proxy)
    ├── Open-WebUI          (LLM chat UI)
    └── Vaultwarden         (password manager)
```

## Decision

Split `docker-runtime-lv3` into three purpose-scoped VMs aligned to workload
class. The VMID and IP of the original VM are retained so that routing changes
are minimised.

### New topology (after this ADR)

```
runtime-comms-lv3 (NEW, VMID 121, 10.10.10.21)
8 vCPU / 24 GB RAM / 256 GB disk
│
├── Mattermost          (ChatOps + message attachments)
├── Matrix-Synapse      (federated IM)
├── mautrix-discord     (bridge)
├── mautrix-whatsapp    (bridge)
├── LiveKit             (WebRTC video/audio)
└── Redpanda            (Kafka broker)

runtime-apps-lv3 (NEW, VMID 122, 10.10.10.22)
8 vCPU / 16 GB RAM / 192 GB disk
│
├── Nextcloud           (file sync/share)
├── MinIO               (object storage)
├── Outline             (team wiki)
├── Plane               (project management)
├── Vikunja             (task management)
├── N8N                 (workflow automation)
├── NetBox              (IPAM/DCIM)
├── Directus            (CMS/API)
├── Label Studio        (ML annotation)
├── Paperless           (document management)
├── Gotenberg           (PDF generation)
├── Tika                (content extraction)
├── Browser-Runner      (headless browser)
├── Searxng             (meta search)
├── Excalidraw          (collaborative drawing)
├── ChangeDetection     (website monitor)
├── Woodpecker CI       (CI/CD server + agent)
├── Portainer           (Docker management UI)
└── Dozzle              (Docker log viewer)

docker-runtime-lv3 → repurposed as runtime-data-lv3 (KEEP, VMID 120, 10.10.10.20)
4 vCPU / 12 GB RAM / 128 GB disk  (downsized after migration)
│
├── Langfuse            (LLM observability)
├── Flagsmith           (feature flags)
├── Plausible           (analytics)
├── Lago                (billing)
├── Glitchtip           (error tracking)
├── Dify                (LLM orchestration)
├── Superset            (BI)
├── Grist               (spreadsheets)
├── Typesense           (search engine)
├── One-API             (OpenAI proxy)
├── Open-WebUI          (LLM chat UI)
└── Vaultwarden         (password manager)

(Unchanged)
runtime-ai-lv3      (VMID 190, 10.10.10.90)  — Ollama, Piper, AI inference
runtime-general-lv3 (VMID 191, 10.10.10.91)  — Uptime Kuma, Homepage, Mailpit
runtime-control-lv3 (VMID 192, 10.10.10.92)  — Keycloak, OpenBao, Step-CA,
                                                 OpenFGA, Gitea, Harbor,
                                                 Semaphore, Temporal, Windmill,
                                                 API Gateway, Mail Platform
```

### VM resource summary

| VM | VMID | IP | vCPU | RAM | Disk | Role |
|---|---|---|---|---|---|---|
| `runtime-comms-lv3` | 121 | 10.10.10.21 | 8 | 24 GB | 256 GB | Real-time communications |
| `runtime-apps-lv3` | 122 | 10.10.10.22 | 8 | 16 GB | 192 GB | Collaborative apps + CI/CD |
| `docker-runtime-lv3` (→ `runtime-data`) | 120 | 10.10.10.20 | 4 | 12 GB | 128 GB | Analytics + observability + data |
| `runtime-ai-lv3` | 190 | 10.10.10.90 | — | 16 GB | — | AI/ML inference (unchanged) |
| `runtime-general-lv3` | 191 | 10.10.10.91 | — | 12 GB | — | General utilities (unchanged) |
| `runtime-control-lv3` | 192 | 10.10.10.92 | — | 12 GB | — | Control plane (unchanged) |

### Service-to-VM assignment table

| Service | Current VM | New VM | Rationale |
|---|---|---|---|
| Mattermost | docker-runtime-lv3 (120) | runtime-comms-lv3 (121) | Real-time messaging, large attachment store |
| Matrix-Synapse | docker-runtime-lv3 (120) | runtime-comms-lv3 (121) | Federated IM, persistent WebSocket |
| mautrix-discord | docker-runtime-lv3 (120) | runtime-comms-lv3 (121) | Bridge for Mattermost/Matrix |
| mautrix-whatsapp | docker-runtime-lv3 (120) | runtime-comms-lv3 (121) | Bridge for Mattermost/Matrix |
| LiveKit | docker-runtime-lv3 (120) | runtime-comms-lv3 (121) | WebRTC, kernel-level network pressure |
| Redpanda | docker-runtime-lv3 (120) | runtime-comms-lv3 (121) | Kafka broker, sequential I/O intensive |
| Nextcloud | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | File sync, shares MinIO storage |
| MinIO | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | Object storage, co-located with consumers |
| Outline | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | Wiki, moderate bursty workload |
| Plane | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | Project management |
| Vikunja | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | Task management |
| N8N | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | Workflow automation |
| NetBox | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | IPAM/DCIM |
| Directus | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | CMS/API |
| Label Studio | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | ML annotation |
| Paperless | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | Document management |
| Gotenberg | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | PDF generation |
| Tika | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | Content extraction |
| Browser-Runner | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | Headless browser |
| Searxng | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | Meta search |
| Excalidraw | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | Collaborative drawing |
| ChangeDetection | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | Website monitoring |
| Woodpecker CI | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | CI/CD — CPU spikes isolated here |
| Portainer | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | Docker management UI |
| Dozzle | docker-runtime-lv3 (120) | runtime-apps-lv3 (122) | Docker log viewer |
| Langfuse | docker-runtime-lv3 (120) | docker-runtime-lv3 (120) | LLM observability — stays |
| Flagsmith | docker-runtime-lv3 (120) | docker-runtime-lv3 (120) | Feature flags — stays |
| Plausible | docker-runtime-lv3 (120) | docker-runtime-lv3 (120) | Analytics — stays |
| Lago | docker-runtime-lv3 (120) | docker-runtime-lv3 (120) | Billing — stays |
| Glitchtip | docker-runtime-lv3 (120) | docker-runtime-lv3 (120) | Error tracking — stays |
| Dify | docker-runtime-lv3 (120) | docker-runtime-lv3 (120) | LLM orchestration — stays |
| Superset | docker-runtime-lv3 (120) | docker-runtime-lv3 (120) | BI — stays |
| Grist | docker-runtime-lv3 (120) | docker-runtime-lv3 (120) | Spreadsheets — stays |
| Typesense | docker-runtime-lv3 (120) | docker-runtime-lv3 (120) | Search engine — stays |
| One-API | docker-runtime-lv3 (120) | docker-runtime-lv3 (120) | OpenAI proxy — stays |
| Open-WebUI | docker-runtime-lv3 (120) | docker-runtime-lv3 (120) | LLM chat UI — stays |
| Vaultwarden | docker-runtime-lv3 (120) | docker-runtime-lv3 (120) | Password manager — stays |

### Grouping rationale

**`runtime-comms-lv3` — real-time communication backbone**

Mattermost, Matrix-Synapse, LiveKit, and Redpanda share three characteristics
that make them a natural isolation boundary:

1. They maintain long-lived stateful connections (WebSockets, Kafka consumer
   groups, WebRTC peer connections) that are sensitive to process-level jitter
   caused by other services competing for CPU or memory.
2. They impose high-throughput I/O: Redpanda writes Kafka partition logs
   sequentially; Mattermost accumulates message attachments over months;
   LiveKit sustains kernel UDP processing for media streams.
3. Their storage scaling trajectory is driven by user adoption rather than
   deployments, so disk capacity must be sized independently of the object
   storage that Nextcloud and MinIO share.

The 256 GB disk is sized to accommodate Mattermost attachment growth (estimated
>20 GB/year at current usage) and Redpanda partition log retention without
competing for the overlay2 storage used by CI build layers.

**`runtime-apps-lv3` — collaborative productivity and CI/CD**

This group contains services with moderate, bursty workloads that are tolerant
of CPU competition with each other (they are not latency-sensitive at the
millisecond level). Grouping MinIO with Nextcloud, Directus, and Paperless is
intentional: all four consume MinIO for object storage, and keeping them on the
same VM reduces cross-VM traffic for presigned URL flows.

Woodpecker CI is placed here rather than on `runtime-control-lv3` because its
resource spikes are appropriate to share with batch-oriented productivity tools
rather than the latency-sensitive control plane (Keycloak, OpenBao).

**`docker-runtime-lv3` repurposed as `runtime-data`**

The remaining services — analytics, observability pipelines, LLM orchestration,
and billing — share bulk-write patterns (Plausible ingests event streams;
Langfuse writes trace spans; Glitchtip buffers exception payloads) with lower
user-facing latency requirements than communications or file-sync services.
They collectively use far less disk than the migrated groups, enabling the VM
to be downsized to 128 GB after migration is complete.

Retaining VMID 120 and IP 10.10.10.20 for this VM avoids changes to
PostgreSQL host-var references, the Tailscale proxy configuration, and any
service that uses a hardcoded IP for a data-tier service.

## Places That Need to Change

---

### 1. `inventory/hosts.yml`

**What:** Add `runtime-comms-lv3` and `runtime-apps-lv3` to the `lv3_guests`
group. Add new host groups `runtime_comms` and `runtime_apps`.

```yaml
# Under lv3_guests:
runtime-comms-lv3:
  ansible_host: 10.10.10.21

runtime-apps-lv3:
  ansible_host: 10.10.10.22

# New groups:
runtime_comms:
  hosts:
    runtime-comms-lv3: {}

runtime_apps:
  hosts:
    runtime-apps-lv3: {}
```

**Why:** Ansible cannot target the new VMs without hosts entries. The group
names are used by service playbooks to scope execution.

---

### 2. `inventory/host_vars/proxmox_florin.yml`

**What:**

a. **Add VM definitions** for `runtime-comms-lv3` (VMID 121) and
`runtime-apps-lv3` (VMID 122) to the `proxmox_guests` list, following
the same spec shape as existing runtime VMs:

```yaml
- vmid: 121
  name: runtime-comms-lv3
  role: runtime-comms
  template_key: lv3-debian-base
  ipv4: 10.10.10.21
  cidr: 24
  gateway4: 10.10.10.1
  macaddr: BC:24:11:C7:84:1C   # allocate from the managed pool
  cores: 8
  memory_mb: 24576
  disk_gb: 256
  tags:
    - runtime
    - comms
    - lv3

- vmid: 122
  name: runtime-apps-lv3
  role: runtime-apps
  template_key: lv3-debian-base
  ipv4: 10.10.10.22
  cidr: 24
  gateway4: 10.10.10.1
  macaddr: BC:24:11:C7:84:1D   # allocate from the managed pool
  cores: 8
  memory_mb: 16384
  disk_gb: 192
  tags:
    - runtime
    - apps
    - lv3
```

b. **Add Tailscale TCP proxy entries** for both new VMs so `service_health_tool.py`
and operator tools can reach management ports over Tailscale without going through
the public edge.

c. **Update `docker-runtime-lv3`** VM spec: after migration is validated, reduce
`memory_mb` to 12288 and `disk_gb` to 128.

---

### 3. `inventory/group_vars/platform.yml`

**What:**

a. **Update per-service `owning_vm` and upstream IP** for every service migrating
to a new VM. The Jinja2 `selectattr` pattern already used for Coolify (see ADR 0340
Finding 2) should be extended so upstream IPs resolve from the `proxmox_guests` list
rather than hardcoded addresses:

```yaml
private_ip: >-
  {{ (proxmox_guests | selectattr('name', 'equalto', 'runtime-comms-lv3')
      | map(attribute='ipv4') | first) }}
```

b. **Add new group_vars blocks** for `runtime_comms` and `runtime_apps` groups
with appropriate `docker_runtime_group` and `service_partition` values.

c. **Update the `platform_guest_catalog`** to include entries for both new VMs.

---

### 4. New playbooks: `playbooks/services/runtime-comms.yml` and `playbooks/services/runtime-apps.yml`

**What:** Create two new service playbooks following the same structure as
existing runtime service playbooks:

- Play 1: Provision VM via `lv3.platform.proxmox_guests`
- Play 2: Converge Docker runtime (`lv3.platform.docker_runtime`)
- Play 3: Converge guest observability (`lv3.platform.guest_observability`)
- Play 4: Converge firewall (`lv3.platform.linux_guest_firewall`)
- Play 5: Deploy assigned services (per-service roles)
- Play 6: Verify health probes

---

### 5. `playbooks/docker-runtime.yml`

**What:** Remove service roles for the 31 services migrating to the two new VMs.
After migration, this playbook deploys only the 12 data/analytics services
remaining on VMID 120. Rename the play's `hosts:` target to `runtime_data` once
the new group alias is established, but keep backward-compatible targeting for
the transition period.

---

### 6. Per-service playbooks (`playbooks/services/`)

**What:** Update the `hosts:` target in each affected service playbook to point
to the correct new group. For example:

- `playbooks/services/mattermost.yml`: `hosts: runtime_comms`
- `playbooks/services/nextcloud.yml`: `hosts: runtime_apps`
- `playbooks/services/langfuse.yml`: `hosts: runtime_data` (or existing group)

---

### 7. NGINX edge config (`inventory/group_vars/platform.yml` — route definitions)

**What:** Update the upstream IP for every service that moves to a new VM.
Representative examples:

| Service | Old upstream | New upstream |
|---|---|---|
| Mattermost | `http://10.10.10.20:8065` | `http://10.10.10.21:8065` |
| Matrix-Synapse | `http://10.10.10.20:8008` | `http://10.10.10.21:8008` |
| LiveKit | `http://10.10.10.20:7880` | `http://10.10.10.21:7880` |
| Redpanda Console | `http://10.10.10.20:8080` | `http://10.10.10.21:8080` |
| Nextcloud | `http://10.10.10.20:80` | `http://10.10.10.22:80` |
| MinIO | `http://10.10.10.20:9001` | `http://10.10.10.22:9001` |
| Woodpecker CI | `http://10.10.10.20:8000` | `http://10.10.10.22:8000` |
| Outline | `http://10.10.10.20:3000` | `http://10.10.10.22:3000` |

All upstream IP references should be driven from the Jinja2 `selectattr`
pattern (see item 3a above) rather than hardcoded addresses, to prevent
the dual-maintenance risk documented in ADR 0340 DRY-5.

---

### 8. `config/health-probe-catalog.json`

**What:** Add health probe entries for `runtime-comms-lv3` (VMID 121,
`10.10.10.21`) and `runtime-apps-lv3` (VMID 122, `10.10.10.22`), including
per-service probes for each migrated service on its new host.

---

### 9. `config/service-redundancy-catalog.json`

**What:** Add entries for both new VMs with their backup scope, restart domain,
and failure domain classification.

---

### 10. Monitoring scrape config (`config/prometheus/`)

**What:** Add Prometheus scrape targets for node exporter and Docker metrics on
both new VMs.

---

### 11. Backup scope

**What:** Add `runtime-comms-lv3` and `runtime-apps-lv3` to the Proxmox Backup
Server (PBS) schedule. The Mattermost attachment store and Nextcloud data volumes
require file-level backup coverage via Restic in addition to VM-level snapshots.

---

### 12. `docs/adr/.index.yaml`

**What:** Add this ADR (0347) to the machine-readable index with tags:
`infrastructure`, `vm-separation`, `reliability`, `blast-radius`, `docker`,
`runtime`.

---

### 13. `workstreams.yaml`

**What:** Register a new workstream entry `ws-0347` before the first commit on
the implementation branch.

---

### 14. `tests/` — new and updated test files

**What:**

- `tests/test_runtime_comms_playbook.py` — assert play structure, guest spec
  presence in `host_vars/proxmox_florin.yml`, service role inclusion, and
  firewall role presence.
- `tests/test_runtime_apps_playbook.py` — same pattern for `runtime-apps-lv3`.
- `tests/test_docker_runtime_playbook.py` — assert that services migrated to
  new VMs are NOT present in the `docker-runtime.yml` play after migration.
- `tests/test_nginx_edge_publication_role.py` — assert upstream IPs for
  Mattermost, Nextcloud, and Woodpecker CI reference the new VM IPs.

## Consequences

### Positive

**Blast radius reduction.** A Docker daemon restart on `runtime-comms-lv3`
affects 6 services. The same event on the current `docker-runtime-lv3` affects
approximately 80 services. Maximum single-VM blast radius drops from ~80 to ~25
(the apps VM, the largest group).

**Workload isolation.** Redpanda partition rebalancing and LiveKit media
processing no longer impose latency on Nextcloud file sync or Langfuse query
dashboards. Woodpecker CI build spikes affect only `runtime-apps-lv3`.

**Independent resource tuning.** Each VM can be sized for its actual workload.
The comms VM can grow its disk independently of the apps VM's build layer
storage. Memory limits for analytics services on the data VM no longer compete
with Nextcloud's upload buffer.

**Downsizing the data VM.** Removing 31 services from VMID 120 allows that VM's
RAM to be reduced from 24 GB to 12 GB and disk from 160 GB to 128 GB,
recovering ~12 GB of RAM for the Proxmox host to allocate elsewhere.

**Operational clarity.** Three VMs with clear labels (`comms`, `apps`, `data`)
are easier to reason about than a single VM containing 80 services. On-call
runbooks can target a specific VM class without cross-service blast analysis.

### Negative / Trade-offs

**Migration complexity and maintenance windows.**

The comms migration (Mattermost, Matrix-Synapse) requires a maintenance window:
message attachment stores must be rsync-copied to the new VM before services
start, to avoid message loss during the cutover. Mattermost and Matrix-Synapse
both have documented migration procedures but they are not zero-downtime.

**Two new managed VMs** increase the total managed Proxmox guest count. Each
new VM adds to the backup schedule, Prometheus scrape config, firewall policy
surface, and Ansible inventory maintenance burden.

**NGINX upstream update surface.** Approximately 25 NGINX upstream definitions
must be updated, representing a broad but mechanical change. Any missed upstream
continues to route to the old VM until the migrated service is removed from
VMID 120, which provides a safety window but also creates temporary dual-running
ambiguity.

**Cross-VM service dependencies.** Some services in the apps group call
Typesense (which stays on the data VM) or Mattermost (which moves to comms).
These dependencies cross VM boundaries today and will continue to do so after
the split, but the network path changes from loopback to inter-VM routed. Latency
impact is negligible on the private /24 but operators should be aware.

**MinIO co-location assumption.** This ADR places MinIO on `runtime-apps-lv3`
alongside its primary consumers (Nextcloud, Directus, Paperless). If a service
on a different VM needs MinIO access in the future (e.g., a comms service storing
voice message attachments), that traffic crosses a VM boundary. This is acceptable
given current usage patterns but should be revisited if MinIO becomes a
platform-wide shared primitive.

## Implementation Order

1. **Provision `runtime-comms-lv3`** (VMID 121, 10.10.10.21) via `proxmox_guests`.
2. **Install Docker runtime** on `runtime-comms-lv3` via `lv3.platform.docker_runtime`.
3. **Migrate communications services** to `runtime-comms-lv3`:
   - Schedule maintenance window; notify operators via Mattermost (pre-migration).
   - Rsync Mattermost data volumes and Matrix-Synapse media store to new VM.
   - Start services on `runtime-comms-lv3`; verify health probes pass.
   - Stop services on `docker-runtime-lv3` (120).
4. **Update NGINX upstreams** for comms services (Mattermost, Matrix-Synapse,
   LiveKit, Redpanda Console).
5. **Verify comms services** end-to-end via public subdomains and Uptime Kuma probes.
6. **Provision `runtime-apps-lv3`** (VMID 122, 10.10.10.22) via `proxmox_guests`.
7. **Install Docker runtime** on `runtime-apps-lv3`.
8. **Migrate apps services** to `runtime-apps-lv3`:
   - Nextcloud and MinIO data volumes require rsync with a brief service stop.
   - Other stateless or DB-backed services (Woodpecker, Outline, Plane) can be
     migrated with minimal downtime (start on new VM, drain old, remove from old).
   - Start services on `runtime-apps-lv3`; verify health probes pass.
   - Stop services on `docker-runtime-lv3` (120).
9. **Update NGINX upstreams** for apps services (Nextcloud, MinIO, Woodpecker CI,
   Outline, and all remaining moved services).
10. **Verify apps services** end-to-end.
11. **Remove migrated services** from `docker-runtime-lv3` Compose configurations.
12. **Downsize `docker-runtime-lv3`** resources (RAM 24 GB → 12 GB, disk 160 GB → 128 GB)
    after at least 72 hours of validated steady-state operation.
13. **Update `versions/stack.yaml`** and cut live-apply receipts for all three VMs.

## Related ADRs

- ADR 0023: Docker Runtime VM Baseline (original `docker-runtime-lv3` design)
- ADR 0025: Compose-managed Runtime Stacks
- ADR 0029: Dedicated Backup VM (backup coverage implications)
- ADR 0067: Guest Network Policy Enforcement (firewall policies for new VMs)
- ADR 0329: Shared Docker Runtime Bridge-Chain Checks (motivating incident for blast radius reduction)
- ADR 0340: Dedicated Coolify Apps VM Separation (same VM-separation pattern)
- ADR 0346: PostgreSQL Domain Clustering (companion split for the database tier)
