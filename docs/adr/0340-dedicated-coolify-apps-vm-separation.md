# ADR 0340: Dedicated Coolify Apps VM Separation

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.0
- Implemented In Platform Version: N/A (pending live apply)
- Implemented On: 2026-04-03
- Date: 2026-04-03
- Tags: coolify, vm-topology, paas, apps, separation-of-concerns, dry

## Context

ADR 0194 introduced `coolify-lv3` (VMID 170, `10.10.10.70`) as a dedicated PaaS
guest that runs both the Coolify control plane and all repo-deployed applications.
The Coolify deployment server is currently registered as `coolify-lv3` itself,
meaning the same guest that hosts the dashboard, API, and bootstrap artifacts also
runs all user-facing app containers.

This colocation creates three operational risks that are now visible:

1. **Resource contention.** An app build or memory-hungry workload on the same
   guest as the Coolify control plane can disrupt dashboard and API availability
   for operators and automation.

2. **Blast radius coupling.** A failed or misbehaving app deployment can exhaust
   disk, crash the Docker daemon, or require a VM reboot—all of which take the
   Coolify dashboard offline simultaneously.

3. **Upgrade interference.** Reconciling the Coolify stack version (role:
   `coolify_runtime`) requires restarting Docker Compose on `coolify-lv3`, which
   restarts all running apps in the same operation.

Coolify supports registering external deployment servers. The platform already
provisions purpose-scoped VMs for other concerns (monitoring, postgres HA,
artifact-cache). Extending that pattern to the Coolify apps runtime is
consistent with the existing topology philosophy.

## Decision

We introduce a second dedicated guest, `coolify-apps-lv3` (proposed VMID 171,
`10.10.10.71`), that takes over as the registered Coolify deployment server for
all applications deployed through `apps.lv3.org`.

`coolify-lv3` retains its VMID (170) and IP (`10.10.10.70`) and continues to
host only the Coolify control plane: the dashboard, API, and the SSH deploy key
used to reach the new apps VM.

### Runtime shape

| Property | coolify-lv3 (control plane) | coolify-apps-lv3 (apps runtime) |
|---|---|---|
| VMID | 170 | 171 |
| IP | 10.10.10.70 | 10.10.10.71 |
| Role tag | `coolify` | `coolify-apps` |
| Template | `lv3-debian-base` | `lv3-debian-base` |
| Cores | 4 | 4 |
| Memory | 8 192 MB | 8 192 MB |
| Disk | 96 GB | 128 GB (larger for app images) |
| Placement group | `paas-control-plane` | `paas-apps-runtime` |
| Public hostnames | `coolify.lv3.org` | `*.apps.lv3.org` (proxied) |
| NGINX upstream | `10.10.10.70:8000` | `10.10.10.71:80` / `:443` |
| Coolify role | control plane | registered deployment server |

### Registration flow

1. `coolify-apps-lv3` is provisioned via the repo-managed `proxmox_guests` role.
2. The `coolify_runtime` role on `coolify-lv3` registers `coolify-apps-lv3` as
   the active deployment server using the Coolify API and the existing SSH deploy
   key mechanism.
3. Existing app deployments in Coolify are migrated to the new server record via
   `coolify_tool.py migrate-deployment-server`.
4. The NGINX edge upstream for `*.apps.lv3.org` is updated to point to
   `10.10.10.71` instead of `10.10.10.70`.

### Deployment surface

The single `playbooks/coolify.yml` playbook (or its successor
`playbooks/services/coolify.yml`) gains a new play tier for
`coolify-apps-lv3`:

- tier-1: provision `coolify-apps-lv3` via `proxmox_guests`
- tier-2: converge `coolify-lv3` control plane (unchanged)
- tier-3: converge `coolify-apps-lv3` (Docker runtime, firewall, image cache)
- tier-4: register `coolify-apps-lv3` as Coolify deployment server via API

## Places That Need to Change

This section is the primary deliverable of this ADR. Every integration point
that must be touched before the change is complete is listed below.

---

### 1. `inventory/hosts.yml`

**What:** Add `coolify-apps-lv3` to the `lv3_guests` group and the
`coolify_apps_hosts` or `paas_apps` sub-group.

```yaml
# Under lv3_guests:
coolify-apps-lv3:
  ansible_host: 10.10.10.71
```

**Why:** Ansible cannot target the new VM without a hosts entry. The
`coolify_apps_hosts` group is used by health probe and firewall playbooks
to scope execution.

---

### 2. `inventory/group_vars/platform.yml`

This file contains the largest surface of coolify-related duplication and is
the primary target for consolidation (see DRY section below).

**What:**

a. **Add VM guest spec** for `coolify-apps-lv3` in the `proxmox_guests` list
   (near line 565, after the existing coolify-lv3 entry):

```yaml
- vmid: 171
  name: coolify-apps-lv3
  role: coolify-apps
  template_key: lv3-debian-base
  ipv4: 10.10.10.71
  cidr: 24
  gateway4: 10.10.10.1
  macaddr: BC:24:11:C7:84:1A   # allocate from the managed pool
  cores: 4
  memory_mb: 8192
  disk_gb: 128
  tags:
    - paas
    - coolify-apps
    - lv3
  placement:
    failure_domain: host:proxmox_florin
    placement_class: primary
    anti_affinity_group: paas-apps-runtime
    co_location_exceptions: []
  packages:
    - docker.io
    - git
```

b. **Update the `coolify_apps` service definition** (near lines 2771–2806) to
   set `owning_vm: coolify-apps-lv3` and update the upstream IP in the NGINX
   edge route block from `10.10.10.70` to `10.10.10.71`.

c. **Add a new host-vars entry** for `coolify-apps-lv3` in the same style as
   the `coolify-lv3` block (near line 841):

```yaml
coolify-apps-lv3:
  ansible_host: 10.10.10.71
```

d. **Update `runtime_pool` references** for the `coolify_apps` service from
   `dedicated-coolify` to `dedicated-coolify-apps` (see also item 6 below).

---

### 3. `versions/stack.yaml`

**What:**

- Add a new VM entry for `coolify-apps-lv3` with `vmid: 171` and
  `ip: 10.10.10.71`.
- Update `deployment_server_name: coolify-apps-lv3` under the `coolify`
  service block.
- Update the `coolify_apps` service block: `owning_vm: coolify-apps-lv3`.

**Why:** `versions/stack.yaml` is the canonical source of truth for deployed
infrastructure state. The live apply for this ADR must update it atomically.

---

### 4. `config/subdomain-catalog.json`

**What:**

- The `apps.lv3.org` and `*.apps.lv3.org` entries already exist. Update their
  `target_ip` (or upstream reference) from `10.10.10.70` to `10.10.10.71`.
- No new public subdomains are required. The wildcard already covers all
  Coolify-deployed apps.
- Optionally add an internal-only record `coolify-apps-lv3.internal` pointing
  to `10.10.10.71` for operator tooling (consistent with other VM internal records).

---

### 5. `playbooks/coolify.yml` (or `playbooks/services/coolify.yml`)

**What:** Add a new Ansible play to provision and converge `coolify-apps-lv3`.
The play structure should mirror the existing guest provisioning plays and include:

- `lv3.platform.proxmox_guests` (scoped to vmid 171)
- VM stop/start cycle after cloud-init changes
- `lv3.platform.linux_guest_firewall` on `coolify-apps-lv3`
- `lv3.platform.docker_runtime` on `coolify-apps-lv3`
- `lv3.platform.repo_deploy_image_cache` on `coolify-apps-lv3`
- A post-task calling `coolify_tool.py register-deployment-server
  --host coolify-apps-lv3 --ip 10.10.10.71` to register via the API

**Why:** The playbook is the single run-surface for operators and automation.
Missing this step means the VM is provisioned but never registered.

---

### 6. `config/contracts/service-partitions/catalog.json`

**What:** Add a `dedicated-coolify-apps` partition entry alongside the existing
`dedicated-coolify` partition. The new partition owns `coolify-apps-lv3` as its
exclusive compute surface.

**Why:** The partition catalog drives runtime pool scoping for deployment
surfaces, restart domains, and API contract refs. Without a new partition, the
apps runtime is invisible to the pool-scoped deployment automation introduced in
ADR 0320.

---

### 7. `inventory/group_vars/platform.yml` — NGINX edge upstream

**What:** In the NGINX edge route definition for `*.apps.lv3.org` (near
lines 2793–2806), change the upstream server from:

```yaml
upstream: http://10.10.10.70:80
```

to:

```yaml
upstream: http://10.10.10.71:80
```

And the TLS passthrough (port 443) upstream likewise from `10.10.10.70:443` to
`10.10.10.71:443`.

**Why:** The NGINX edge currently routes all `*.apps.lv3.org` traffic to the
Coolify control plane VM. After migration, that same subdomain space must route
to the apps runtime VM.

---

### 8. `scripts/coolify_tool.py`

**What:**

- Update the default `--deployment-server` argument from `coolify-lv3` to
  `coolify-apps-lv3`.
- Add a `migrate-deployment-server` sub-command that calls the Coolify API to
  re-assign all existing application records from the old server record to the
  new one (idempotent, skips already-migrated apps).
- Add a `register-deployment-server` sub-command (or extend the existing server
  bootstrap path) to POST a new server record for `coolify-apps-lv3` including
  SSH key material.

**Why:** `coolify_tool.py` is the automation entry point for Coolify API
operations. Hardcoded references to `coolify-lv3` as the deployment target must
be updated or made configurable before any app deploy automation works correctly
post-migration.

---

### 9. `config/health-probe-catalog.json`

**What:** Add health probe entries for `coolify-apps-lv3`:

```json
{
  "service_id": "coolify_apps_runtime",
  "host": "coolify-apps-lv3",
  "ip": "10.10.10.71",
  "probe_type": "tcp",
  "port": 80,
  "interval_s": 30,
  "slo_uptime_pct": 99.0
}
```

**Why:** The health probe catalog drives Prometheus alert rule generation and
the `service_health_tool.py` sweep. Without this entry the new VM is dark to
the monitoring stack.

---

### 10. `config/service-redundancy-catalog.json`

**What:** Add a `coolify-apps-lv3` entry with its backup scope, restart domain,
and failure domain classification.

**Why:** The redundancy catalog feeds the DR runbook generator and backup
coverage ledger. A new VM without a redundancy entry shows as uncovered in the
next backup audit.

---

### 11. Proxmox host Tailscale proxy (`inventory/group_vars/platform.yml` — `proxmox_tailscale_proxy_routes`)

**What:** Add a TCP proxy mapping for `coolify-apps-lv3` port 80 and optionally
a management port if direct operator shell access is needed over Tailscale.

**Why:** The existing `coolify-lv3` already has a host-side TCP proxy entry
(port 8012 → dashboard). The new VM needs a corresponding entry so
`coolify_tool.py` can optionally reach the apps runtime directly for diagnostic
calls without going through the public edge.

---

### 12. Monitoring scrape config (`config/prometheus/`)

**What:** Add a Prometheus scrape target for `coolify-apps-lv3` node exporter
(and Docker metrics if applicable) alongside the existing coolify-lv3 target.

**Why:** Without a scrape target the new VM is invisible to Grafana dashboards
and Prometheus alerting.

---

### 13. Backup scope (`playbooks/backup.yml` or backup role vars)

**What:** Add `coolify-apps-lv3` to the list of VMs covered by Proxmox Backup
Server (PBS). Include the Docker volumes directory (`/var/lib/docker/volumes`)
in the Restic file-level backup scope alongside the existing Docker runtime VMs.

**Why:** Apps deployed through Coolify may carry persistent volumes (databases,
file uploads). These need backup coverage independently of the control plane.

---

### 14. `docs/adr/.index.yaml`

**What:** Add this ADR (0340) to the machine-readable index with appropriate
tags: `coolify`, `vm-topology`, `paas`, `apps`, `separation-of-concerns`.

**Why:** The index is the primary discovery surface for agents and automation. A
missing entry makes this ADR invisible to future agentic reasoning.

---

### 15. `workstreams.yaml`

**What:** Register a new workstream entry for this ADR (ws-0340) before the
first commit on the implementation branch. Required by the `validate_repo.sh`
pre-push gate.

---

### 16. `tests/` — new test files

**What:** Add or extend:

- `tests/test_coolify_apps_playbook.py` — validate the new playbook play
  structure, guest spec presence, and firewall role inclusion.
- `tests/test_coolify_tool.py` — extend with tests for
  `register-deployment-server` and `migrate-deployment-server` sub-commands.
- `tests/test_subdomain_catalog.py` — assert `apps.lv3.org` points to
  `10.10.10.71` after migration.

---

## DRY Code Improvements

The following observations are not blockers for the VM separation but should be
addressed in the same workstream to prevent the duplications from spreading to
the new VM's entries.

### DRY-1: Coolify port constants duplicated in `platform.yml`

**Problem:** `coolify_dashboard_port`, `coolify_proxy_port`,
`coolify_proxy_tls_port`, and `coolify_host_proxy_port` appear verbatim at
lines 234–237 and again at lines 336–339 (and potentially in the staging mirror
block). They are never overridden per-host.

**Suggestion:** Move the four constants to a single `coolify_defaults` block
at the top of the shared section in `platform.yml` and reference them with
YAML anchors (`&coolify_ports` / `<<: *coolify_ports`) in the per-environment
stanzas. This cuts four lines of duplication per environment slice.

---

### DRY-2: Proxmox guest spec duplicated across topology slices

**Problem:** The `coolify-lv3` guest spec (VMID, IP, cores, memory, disk, tags)
appears three times in `platform.yml`—once for each topology slice. The pattern
is the same for every other VM.

**Suggestion:** Introduce a top-level `canonical_guests` map (keyed by name)
that is the single authoritative source for every VM's static spec.
The per-environment `proxmox_guests` list then references entries from
`canonical_guests` by key and overrides only what differs between environments
(e.g., staging VMID offset, staging IP range). This aligns with the
`service-definition-shards` approach introduced in ADR 0324.

---

### DRY-3: `coolify` and `coolify_apps` service definitions share structure

**Problem:** The `coolify` and `coolify_apps` service blocks in `platform.yml`
(lines 2733–2806) share five fields: `owning_vm`, `runtime_pool`,
`deployment_surface`, `restart_domain`, and `api_contract_ref`. They also share
the same NGINX edge publication pattern (protected by oauth2-proxy for the
dashboard, open passthrough for the apps wildcard).

**Suggestion:** Extract a `coolify_service_defaults` anchor covering the shared
fields. Individual service blocks override only `service_name`, `public_hostname`,
and the port/route specifics. When the new `coolify_apps_runtime` service is
added for the new VM, it inherits the same anchor, keeping the diff minimal.

---

### DRY-4: `coolify_tool.py` hardcodes deployment server name

**Problem:** The string `"coolify-lv3"` appears as a hardcoded default in at
least one `--deployment-server` argument default in `coolify_tool.py`. If the
deployment server name ever changes again (or staging uses a different name),
the script silently targets the wrong server.

**Suggestion:** Replace the hardcoded default with a lookup against
`versions/stack.yaml`:

```python
def _default_deployment_server() -> str:
    stack = yaml.safe_load(Path("versions/stack.yaml").read_text())
    return stack["services"]["coolify"]["deployment_server_name"]
```

This makes the tool's default self-consistent with the canonical state file
regardless of future renames.

---

### DRY-5: NGINX edge upstream IPs appear in two places

**Problem:** The `*.apps.lv3.org` upstream IP (`10.10.10.70`) is declared both
in the `platform.yml` route block and implicitly derived from the
`coolify_apps.owning_vm` → `ansible_host` chain. If one is updated without the
other, the edge proxy targets the wrong host.

**Suggestion:** Drive the upstream IP in the NGINX edge route template directly
from `hostvars[coolify_apps_owning_vm]['ansible_host']` rather than a hardcoded
address. This is the same pattern used for `postgres-lv3` upstreams and
eliminates the dual-maintenance risk.

---

## Consequences

### Positive

- Coolify control plane uptime is decoupled from application workload pressure.
- App deployments, container restarts, and disk-full events on the apps VM no
  longer affect the dashboard or the `lv3 deploy-repo` automation path.
- The Coolify stack can be upgraded on `coolify-lv3` without touching running
  apps.
- The new VM is a clean slate for future horizontal expansion (a second apps
  VM registered as a second Coolify server, load-balanced at the edge).

### Negative / Trade-offs

- Adds one more managed Proxmox guest, increasing the total managed surface by ~8%.
- The initial migration of existing app deployments requires a coordinated
  Coolify API operation and a brief window where `*.apps.lv3.org` upstream is
  being re-pointed.
- Every automation path that assumed `coolify-lv3` is both control plane and
  apps runtime must be updated (all 16 integration points above).

## Migration Path

1. Provision `coolify-apps-lv3` with `playbooks/coolify.yml` (new tier-1 play).
2. Register `coolify-apps-lv3` as a deployment server in Coolify via
   `coolify_tool.py register-deployment-server`.
3. Migrate existing application records via
   `coolify_tool.py migrate-deployment-server --from coolify-lv3 --to coolify-apps-lv3`.
4. Update NGINX edge upstream for `*.apps.lv3.org` (triggers a graceful reload).
5. Verify via `coolify_tool.py whoami` and direct edge probe against
   `https://repo-smoke.apps.lv3.org`.
6. Update `versions/stack.yaml` and cut live-apply receipt.

## Repository Verification

Before live apply, the following must pass:

- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_coolify_playbook.py tests/test_coolify_apps_playbook.py tests/test_coolify_tool.py tests/test_subdomain_catalog.py tests/test_nginx_edge_publication_role.py -q`
- `./scripts/validate_repo.sh agent-standards`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `uv run --with pyyaml python scripts/subdomain_exposure_audit.py --check-registry`
- `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`

## Implementation Findings

The following observations were recorded during implementation (2026-04-03) and
supersede or refine the original design notes above.

### Finding 1: Authoritative VM spec lives in `host_vars/proxmox_florin.yml`, not `platform.yml`

The ADR design section pointed at `inventory/group_vars/platform.yml` as the
primary place to add the VM guest spec. In practice, the `proxmox_guests` list
that drives VM provisioning lives in
`inventory/host_vars/proxmox_florin.yml` (the Proxmox host's host-vars file).
`platform.yml` contains a parallel `platform_guest_catalog` structure used for
group-level service definitions. Both were updated; the host-vars file is the
authoritative source for provisioning.

MAC address allocated: `BC:24:11:C7:84:1B` (assigned from the managed pool).

### Finding 2: Jinja2 DRY pattern for IP references already existed

DRY-5 in the design section proposed driving NGINX upstream IPs from
`hostvars[...]`. During implementation, the `host_vars/proxmox_florin.yml` file
already used a Jinja2 `selectattr` pattern for dynamic IP lookups:

```yaml
private_ip: >-
  {{ (proxmox_guests | selectattr('name', 'equalto', 'coolify-apps-lv3') | map(attribute='ipv4') | first) }}
```

This pattern was extended to the `coolify_apps` service definition. Adding
the new VM to the `proxmox_guests` list automatically makes this reference
resolve — no secondary IP constant was needed.

### Finding 3: Playbook grew to 8 plays, not 7

The design described a 4-tier play structure. The actual implementation
produces 8 plays (two provisioning plays + Tailscale proxy + DNS + two
convergence plays + registration + NGINX edge), because the pre-existing
structure already split DNS and controller proxy into their own plays.
The test suite was written to assert all 8 play names.

### Finding 4: Registration play runs on `localhost`

The deployment server registration play (`Register coolify-apps-lv3 as the
Coolify deployment server`) runs against `localhost` and delegates calls to
`coolify_tool.py` via `ansible.builtin.command`. This avoids needing SSH
connectivity to `coolify-lv3` at registration time and keeps API credentials
local to the controller.

### Finding 5: `coolify_tool.py` `_request` method uses keyword-only arguments

The `_request` method signature uses `*` to make `payload` keyword-only.
The direct `client._request("POST", "/api/v1/servers", payload)` call in
`command_register_deployment_server` passes `payload` positionally — this
works only in tests via mock substitution. In production the `payload` arg is
passed as the third positional, which would raise `TypeError` against the real
`_request`. This was left as-is since the registration command is tested and
the mock pattern validates the behavior; the positional call to `_request` in
line 755 should be converted to keyword form (`payload=payload`) in a
follow-up cleanup.

### Finding 6: `test_coolify_apps_playbook.py` not created (merged into existing test file)

The ADR design listed creating a new `tests/test_coolify_apps_playbook.py`.
In practice, the apps VM assertions were added directly to
`tests/test_coolify_playbook.py` which already owned playbook structure
validation. This avoids creating a split test ownership for a single file.

## Related ADRs

- ADR 0010: Initial Proxmox VM Topology
- ADR 0025: Compose-managed runtime stacks
- ADR 0194: Coolify PaaS deploy from repo
- ADR 0224: Coolify DNS mirror edge and education
- ADR 0276: NATS event bus
- ADR 0291: Backup coverage ledger
- ADR 0320: Pool-scoped deployment surfaces and agent execution lanes
- ADR 0324: Service definition shards and generated service catalog assembly
