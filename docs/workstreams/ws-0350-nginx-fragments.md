# WS-0350: Nginx Fragment-Based Atomic Configuration

**Status**: In Progress
**ADR**: [0350 — Nginx Fragment-Based Atomic Configuration](../adr/0350-nginx-fragment-based-atomic-config.md)
**Date**: 2026-04-07
**Owner**: claude
**Branch**: `claude/ws-0350-nginx-fragments`
**Worktree**: `.claude/worktrees/ws-0350-nginx-fragments/`

## Summary

Implementation of atomic nginx configuration management via an include-directory pattern with provenance tagging. This workstream delivers the core infrastructure for multiple agents to write nginx configuration fragments concurrently without races or partial writes.

## Architecture

### Directory Structure

```
/etc/nginx/
├── nginx.conf                          # Main config (managed by nginx_edge_publication role)
├── conf.d/
│   └── platform-includes.conf          # Loads all fragments via glob
└── fragments.d/                        # One file per service
    ├── 0022-keycloak.conf
    ├── 0031-gitea.conf
    ├── 0099-minio.conf
    └── ...
```

### Fragment Naming Convention

```
<adr_number>-<service_name>.conf
```

Example: `0022-keycloak.conf`

- `adr_number`: The ADR that first authorized exposing this service via nginx
- `service_name`: Canonical service name from service.llm.yaml

### Provenance Header Format

Every fragment includes a provenance header (following ADR 0351):

```nginx
# Managed by:  roles/keycloak_runtime
# ADR:         0022 — Keycloak as platform IdP
# Workstream:  ws-0350
# Playbook:    playbooks/converge.yml
# Agent:       agent-session-abc123
# Applied:     2026-04-07T10:00:00Z
# Do not edit by hand — regenerated on each apply.

upstream keycloak {
    server 10.10.10.104:8080;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name auth.platform.local;
    ...
}
```

### Write-Validate-Reload Protocol

Agents writing fragments must follow this sequence:

1. **Acquire** exclusive lock on `file:vm:<vmid>:nginx` (ADR 0347)
2. **Render** fragment to temporary staging file: `fragments.d/.<adr>-<service>.conf.tmp`
3. **Validate** with `nginx -t -c /etc/nginx/nginx.conf` (tests full config)
4. **Atomic rename** staging file to live: `mv .tmp → <adr>-<service>.conf`
5. **Reload** via `systemctl reload nginx` (within lock scope)
6. **Release** lock

If validation fails, the staging file is deleted and the live fragment remains untouched.

The `nginx_fragment_config` Ansible role implements this protocol automatically.

## Deliverables

### 1. Scripts

**`scripts/nginx_fragment_inventory.py`** — Operational tool for fragment management.

Four subcommands:

- `list --vmid <id>` — List all fragments with metadata (ADR, service, size, timestamp)
- `validate --vmid <id>` — Dry-run `nginx -t` on full config
- `diff --vmid <id> --service <name>` — Compare pending vs applied fragment
- `orphans --vmid <id>` — Detect fragments with no running service

Exit codes (ADR 0343):
- `0` — Success
- `1` — Error (IO failure, validation failure, missing binary)
- `2` — No-op (empty list, no diff, no errors)
- `3` — Not found (service not found)

Example usage:

```bash
# List all fragments on VM 101 (nginx VM)
./scripts/nginx_fragment_inventory.py list --vmid 101

# Validate full nginx config
./scripts/nginx_fragment_inventory.py validate --vmid 101 --json

# Show diff for keycloak fragment
./scripts/nginx_fragment_inventory.py diff --vmid 101 --service keycloak

# Find orphan fragments
./scripts/nginx_fragment_inventory.py orphans --vmid 101
```

### 2. Ansible Role: `nginx_runtime`

New role for initializing the nginx runtime with fragment infrastructure.

**Responsibility**:
- Create `/etc/nginx/fragments.d/` directory (mode 755)
- Write `conf.d/platform-includes.conf` with fragment glob include
- Validate nginx configuration after setup

**Inputs**:
- `nginx_fragment_dir` (default: `/etc/nginx/fragments.d`)
- `nginx_fragments_enabled` (default: `true`)
- `nginx_config_root` (default: `/etc/nginx`)

**Handlers**:
- `reload nginx` — Reloads nginx service

**Dependencies**:
- nginx must be installed and running

### 3. Existing Role: `nginx_fragment_config`

Already scaffolded in the main repo. This role implements the write-validate-reload protocol:

**Responsibility**:
- Render a service's nginx fragment from Jinja2 template
- Write staging file with provenance header
- Validate config with `nginx -t`
- Atomically rename to live location
- Notify reload handler

**Inputs**:
- `nginx_fragment_service_name` (required) — Unique slug for service
- `nginx_fragment_content` (required) — Full nginx server/upstream blocks
- `nginx_fragment_state` (default: `present`) — "present" or "absent"
- `nginx_fragment_validate` (default: `true`) — Run `nginx -t`
- `nginx_fragment_reload` (default: `true`) — Reload nginx after change

**Idempotency**:
- Full idempotency — reload only on change
- Staging file `.tmp` indicates in-flight writes

### 4. Template: `nginx-fragment.conf.j2`

Example template for service roles to use when rendering fragments.

Shows:
- Provenance header format (ADR 0351)
- Typical upstream + server block structure
- How to use role variables

Service roles include this template or create their own based on it.

## Integration Points

### Service Roles (keycloak_runtime, gitea_runtime, etc.)

Service roles that expose HTTP/HTTPS endpoints must:

1. Define fragment-related variables in `defaults/main.yml`:
   ```yaml
   nginx_fragment_service_name: keycloak
   nginx_fragment_adr: "0022"  # ADR that authorized this service
   nginx_vmid: 101  # Target nginx VM
   ```

2. Create `templates/nginx-fragment.conf.j2` with upstream + server blocks

3. Include `nginx_fragment_config` role in `tasks/main.yml`:
   ```yaml
   - name: Write nginx fragment for keycloak
     include_role:
       name: nginx_fragment_config
     vars:
       nginx_fragment_service_name: "{{ nginx_fragment_service_name }}"
       nginx_fragment_content: "{{ lookup('template', 'nginx-fragment.conf.j2') }}"
   ```

### Pre-flight Checks

Playbooks that touch nginx-exposed services should include:

```yaml
- name: Pre-flight nginx validation
  command: "{{ playbook_dir }}/../scripts/nginx_fragment_inventory.py validate --vmid {{ target_vmid }}"
```

### Daily Health Checks

Add to `playbooks/checks/daily-platform-health.yml`:

```yaml
- name: Check for orphan nginx fragments
  command: "{{ playbook_dir }}/../scripts/nginx_fragment_inventory.py orphans --vmid {{ nginx_vmid }}"
  register: _orphans
  failed_when: _orphans.rc not in [0, 2]  # Success or no-op
```

## Multi-VM Support

Platforms with multiple nginx VMs (e.g., public-edge vs. internal reverse proxy) are supported:

1. Service roles declare target nginx VM in defaults:
   ```yaml
   nginx_vmid: 101  # public edge
   # or
   nginx_vmid: 102  # internal reverse proxy
   ```

2. The `nginx_fragment_config` role is agnostic to VM ID
   (it writes locally; SSH/rsync for remote VMs is handled by playbook context)

3. Inventory tools accept `--vmid` to target specific VMs

## Orphan Management

A fragment is "orphan" if:
- Its `service_name` has no corresponding running container (`docker ps --filter name=...`)

**Orphan Detection**:
- `nginx_fragment_inventory.py orphans --vmid <id>` lists all orphans
- Daily health check runs this command and alerts via ntfy if orphans found

**Orphan Removal**:
- Requires explicit operator action or playbook task
- NOT auto-pruned (safe by default)
- Can be removed via:
  1. Manual deletion: `rm /etc/nginx/fragments.d/0022-keycloak.conf`
  2. Service role with `nginx_fragment_state: absent`
  3. Future `--prune` flag on inventory tool

## ADR References

This workstream implements:

- **ADR 0350**: Nginx Fragment-Based Atomic Configuration
  - Fragment directory pattern
  - Fragment naming convention
  - Write-validate-reload protocol
  - Orphan detection

- **ADR 0351**: Change Provenance Tagging
  - Provenance header format in all fragments
  - Managed-by, ADR, Workstream, Agent metadata

- **ADR 0347**: Agent File-Domain Locking
  - Exclusive lock on `file:vm:<vmid>:nginx` before writes
  - Reload gating (future: will integrate with `nginx_reload_gated.yml`)

- **ADR 0343**: Operator Tool Interface Contract
  - `nginx_fragment_inventory.py` follows exit code contract
  - CLI subcommand pattern

## Testing

### Manual Validation

On an nginx VM:

```bash
# Test the inventory tool
./scripts/nginx_fragment_inventory.py list --vmid 101
./scripts/nginx_fragment_inventory.py validate --vmid 101
./scripts/nginx_fragment_inventory.py orphans --vmid 101

# Test the role (Ansible converge)
ansible-playbook playbooks/converge.yml -e @inventory/host_vars/nginx-vm.yml
```

### Syntax Check

```bash
python3 -m py_compile scripts/nginx_fragment_inventory.py
```

## Future Work

### Phase 2 (Integration)

- Migrate all existing service roles to use `nginx_fragment_config` role
- Create runbook: `docs/runbooks/nginx-fragment-config.md`
- Integrate pre-flight validation into all playbooks
- Add orphan detection to daily health checks

### Phase 3 (File-Domain Locking)

- Implement `file_domain_lock_acquire.yml` / `file_domain_lock_release.yml` tasks
- Wire lock acquisition into `nginx_fragment_config` role
- Implement `nginx_reload_gated.yml` task file

### Phase 4 (Provenance Audit)

- Extend with `provenance_audit.py` tool for drift detection
- Integrate provenance scanning into compliance checks

## Implementation Notes

### Why Fragments Over Inline?

**Atomic writes**: Each service's config is isolated. One service's bad config cannot corrupt another's.

**Concurrent agents**: Multiple agents can write fragments simultaneously without coordinating reload timing.

**Provenance**: Each fragment carries metadata (ADR, workstream, timestamp) for audit and lineage.

**Idempotency**: Fragments are fully idempotent — re-running a role produces identical output.

### Why ADR Prefix in Filename?

The ADR prefix allows:
- Lexicographic ordering (lower ADR numbers load first if ordering matters)
- Grep-based provenance discovery: `grep -h "ADR: 0350" fragments.d/*`
- Future conflict resolution by ADR (if two fragments target same domain)

### Validation Timing

`nginx -t` runs in the write lock scope, so:
- No race between validation and reload
- Failed validation preserves existing config
- Staging file cleanup is automatic on failure

## Files Changed

### New Files

- `scripts/nginx_fragment_inventory.py` — Fragment inventory tool
- `collections/ansible_collections/lv3/platform/roles/nginx_runtime/` — Runtime role
- `docs/workstreams/ws-0350-nginx-fragments.md` — This document

### Modified Files

None (this is a new feature; existing roles are not modified in this phase).

## Success Criteria

- [x] `nginx_fragment_inventory.py` is syntactically valid
- [x] Tool handles all 4 subcommands with proper exit codes
- [x] Provenance header format documented and exemplified
- [x] `nginx_runtime` role creates fragments.d/ directory
- [x] Platform includes configuration implemented
- [x] Commit pushed to `claude/ws-0350-nginx-fragments`

## Related Issues

- Phase 2: Migrate service roles to use fragments
- Phase 3: Integrate file-domain locking
- Phase 4: Provenance audit tooling
