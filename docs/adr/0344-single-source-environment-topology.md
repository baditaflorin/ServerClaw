# ADR 0344: Single-Source Environment Topology

- Status: Accepted
- Implementation Status: Partial
- Implemented In Repo Version: 0.178.4
- Date: 2026-04-04
- Tags: multi-environment, topology, dry, tooling, inventory, configuration

## Context

The platform currently has two parallel sources of truth for environment
topology (node names, VMIDs, IPs, container names, service ports):

1. **Ansible inventory** (`inventory/group_vars/platform.yml`,
   `inventory/host_vars/proxmox_florin.yml`, `inventory/hosts.yml`).
   This is the authoritative source for Ansible plays and roles.

2. **Hand-maintained `topology.yaml`** (`.local/proxmox-api/topology.yaml`).
   This was introduced in ADR 0342 / `proxmox_tool.py` to give non-Ansible
   tools a way to resolve VMIDs, node names, and API URLs per environment.

These two sources will drift. A VMID change in `host_vars/proxmox_florin.yml`
that is not reflected in `topology.yaml` causes `proxmox_tool.py` to operate
on the wrong VM silently. The same problem affects any future tool that reads
from the topology file.

Additionally, the Ansible inventory cannot be read directly by Python tools
at runtime without either:
- Running `ansible-inventory --list` (requires Ansible to be installed and
  takes several seconds), or
- Parsing raw YAML with Jinja2 template resolution — which is impractical
  outside Ansible.

ADR 0183 introduced the multi-environment inventory structure. ADR 0214
(HA Cells, not yet implemented) defines prod/staging/dev as first-class
environment cells. Neither ADR addresses how non-Ansible tools discover
per-environment topology at runtime.

## Decision

Ansible inventory remains the **single authoritative source** for all
environment topology data. Non-Ansible tools read a **generated topology
snapshot** (`scripts/topology-snapshot.json`) that is produced from the
inventory by a generation script and committed to the repository on every
inventory change.

The hand-maintained `.local/proxmox-api/topology.yaml` is deprecated.
After the snapshot generator is implemented, `proxmox_tool.py` and other
tools must read the snapshot instead.

### Topology snapshot schema

The snapshot is a JSON file at a path configured in `inventory/group_vars/all.yml`
(default: `scripts/topology-snapshot.json`):

```json
{
  "schema_version": 1,
  "generated_at": "2026-04-04T00:00:00Z",
  "generated_from": "inventory/",
  "environments": {
    "prod": {
      "node": "Debian-trixie-latest-amd64-base",
      "api_url": "https://100.64.0.1:8006/api2/json",
      "vms": {
        "coolify-lv3":       {"vmid": 170, "ip": "10.10.10.70"},
        "coolify-apps-lv3":  {"vmid": 171, "ip": "10.10.10.71"},
        "postgres-lv3":      {"vmid": 150, "ip": "10.10.10.50"}
      },
      "services": {
        "coolify": {
          "dashboard_port": 8000,
          "db_container": "coolify-db",
          "db_user": "coolify",
          "app_container": "coolify"
        },
        "coolify_apps": {
          "proxy_port": 80
        }
      }
    },
    "staging": {
      "node": "Debian-trixie-latest-amd64-base",
      "api_url": "https://100.64.0.1:8006/api2/json",
      "vms": {
        "coolify-staging":      {"vmid": 270, "ip": "10.10.10.170"},
        "coolify-apps-staging": {"vmid": 271, "ip": "10.10.10.171"}
      },
      "services": {
        "coolify": {
          "dashboard_port": 8000,
          "db_container": "coolify-db",
          "db_user": "coolify",
          "app_container": "coolify"
        }
      }
    }
  }
}
```

### Snapshot generator

`scripts/generate_topology_snapshot.py` reads the Ansible inventory files
directly (without running Ansible) and produces the JSON snapshot.

```
usage: generate_topology_snapshot.py [--inventory <dir>] [--output <path>]
```

The generator runs as part of the `validate_repo.sh` freshness check:
if the snapshot is older than any inventory file it reads from, the check
fails with a message prompting the operator to regenerate.

### Topology resolution in tools

`controller_automation_toolkit.load_topology(path, env) -> dict` replaces
the current hand-written `_resolve_topology` function in `proxmox_tool.py`.

```python
def load_topology(snapshot_path: str | Path, env: str) -> dict:
    """
    Return the topology dict for `env` from the snapshot.
    Raises SystemExit(1) if snapshot not found or env not present.
    """
```

The `--topology-file` flag in `proxmox_tool.py` is kept for backward
compatibility and local override (useful during topology snapshot
bootstrapping), but the default changes to `scripts/topology-snapshot.json`
once the generator is implemented.

### Overlay for local secrets

The `api_url` field may contain a Tailscale IP that is not appropriate to
commit publicly. The generator reads the Tailscale API URL from an overlay
file (`.local/proxmox-api/topology-overlay.json`):

```json
{
  "prod": {"api_url": "https://100.64.0.1:8006/api2/json"},
  "staging": {"api_url": "https://100.64.0.2:8006/api2/json"}
}
```

The overlay is merged last (highest priority) over the generated snapshot.
The committed snapshot contains placeholder values for `api_url` (e.g.
`"https://proxmox.lv3.org:8006/api2/json"`); the overlay supplies the
actual Tailscale address at tool runtime without committing it.

## Places That Need to Change

### 1. `scripts/generate_topology_snapshot.py` — new file

**What:** Generate `scripts/topology-snapshot.json` from inventory.
Parse `inventory/hosts.yml`, `inventory/host_vars/proxmox_florin.yml`,
and `inventory/group_vars/platform.yml` to extract VM specs, service ports,
and container names per environment.

**Why:** This is the foundational piece. Without it the snapshot stays
hand-maintained.

### 2. `scripts/controller_automation_toolkit.py`

**What:** Add `load_topology(snapshot_path, env, overlay_path=None) -> dict`.
Also update `load_auth` to accept optional `topology_key` for pulling `api_url`
from the topology automatically.

### 3. `scripts/proxmox_tool.py`

**What:**
- Change default for `--topology-file` to `scripts/topology-snapshot.json`.
- Replace `_resolve_topology` with a call to `controller_automation_toolkit.load_topology`.
- Keep `--topology-file` override for local use.

### 4. `scripts/validate_repo.sh`

**What:** Add a freshness gate: if `scripts/topology-snapshot.json` is older
than any file in `inventory/`, fail with instructions to run
`python3 scripts/generate_topology_snapshot.py`.

### 5. `.local/proxmox-api/topology.yaml` — deprecated

**What:** Remove usage from `proxmox_tool.py` once the snapshot generator
is available. Document in `docs/proxmox-tool-topology.yaml.example` that
this file is replaced by the snapshot + overlay pattern.

### 6. `docs/proxmox-tool-topology.yaml.example`

**What:** Update to reference the new snapshot + overlay pattern.
Keep as a migration guide for operators upgrading from the old topology.yaml.

## Consequences

### Positive

- VMIDs, IPs, and service ports have exactly one source of truth
  (Ansible inventory). A VMID change in inventory automatically propagates
  to all tools on the next `generate_topology_snapshot.py` run.
- The freshness gate in `validate_repo.sh` catches drift before it causes
  tool failures.
- The overlay pattern keeps Tailscale IPs out of the committed snapshot
  without requiring a secrets manager.
- Adding a new environment (staging, dev) requires only an inventory entry;
  tools discover it automatically from the regenerated snapshot.

### Negative / Trade-offs

- The snapshot generator must be kept up to date with inventory schema
  changes. If a new inventory field is added without updating the generator,
  the snapshot silently omits the field.
- The freshness gate adds latency to `validate_repo.sh` (stat comparison on
  every inventory file).
- During the transition period both the old `topology.yaml` and the new
  snapshot coexist. Tools must be updated in a single migration pass to avoid
  split-brain behaviour.

## Migration Path

1. Implement `generate_topology_snapshot.py` with prod environment support.
2. Commit `scripts/topology-snapshot.json` (with placeholder `api_url`).
3. Create `.local/proxmox-api/topology-overlay.json` with real Tailscale URLs.
4. Update `proxmox_tool.py` to read from snapshot by default.
5. Add freshness gate to `validate_repo.sh`.
6. Deprecate and remove `.local/proxmox-api/topology.yaml` usage.
7. Extend generator to staging environment when staging VMs are provisioned
   (ADR 0214).

## Related ADRs

- ADR 0039: Shared Controller Automation Toolkit
- ADR 0183: Multi-Environment Inventory
- ADR 0214: HA Cells
- ADR 0342: Zero-SSH Guest Operations via Proxmox QAPI
- ADR 0343: Operator Tool Interface Contract
- ADR 0345: Layered Tool Separation
