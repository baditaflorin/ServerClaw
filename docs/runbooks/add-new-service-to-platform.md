# Runbook: Add a New Service to the Platform (ADR 0373)

**Status:** Complete ADR 0373 pattern for all new services
**Audience:** Agent systems, platform developers
**Prerequisites:** Familiarity with ADR 0373, platform service registry

## Overview

All platform services follow the **ADR 0373 Service Registry and Derived Defaults** pattern. This ensures:
- **DRY (Don't Repeat Yourself):** No hardcoded site_dir, compose files, secret paths in 70+ roles
- **IoC (Inversion of Control):** Single source of truth in `platform_service_registry`
- **Programmatic:** AI systems can extend the platform without manual variable duplication
- **Extensible:** Supports docker_compose, system_package, infrastructure, and multi_instance service types

## Step 1: Register the Service in `platform_services.yml`

Edit: `inventory/group_vars/platform_services.yml`

Add an entry under the appropriate alphabetical section:

```yaml
  my_new_service:
    service_type: docker_compose        # OR: system_package, infrastructure, multi_instance
    image_catalog_key: my_new_service_runtime   # (docker_compose only)
    internal_port: 8123
    host_group: docker-runtime      # Which group runs this service
    site_dir: /opt/my-new-service       # (docker_compose only, optional — defaults to /opt/<service>)
    container_name: my-new-service      # (optional — defaults to service name)
    needs_openbao: true                 # Does this service need secret injection?
    needs_postgres: false               # Informational: does it use shared PostgreSQL?

    # For docker_compose services only:
    secret_dir: /etc/lv3/my-new-service  # (optional — defaults to /etc/lv3/<service>)
    local_artifact_dir: my-new-service    # (optional — defaults to service name)

    # For system_package services ONLY:
    state_dirs:
      config: /etc/my-service           # Config directory (e.g., /etc/nginx)
      data: /var/lib/my-service         # Data directory (e.g., /var/lib/nginx)
      secrets: /etc/lv3/my-service      # Secret directory (LV3 pattern)

    # Optional: Extra defaults for compatibility or special cases
    extra_defaults:
      my_service_runtime_package: my-service-package  # For system packages
      my_service_runtime_port: "{{ hostvars['proxmox-host'].platform_port_assignments.my_service_port }}"

    # Optional: DNS, proxy, SSO, TLS config (ADR 0374 cross-cutting concerns)
    dns:
      records:
        - fqdn: myservice.example.com
          type: public
          target_host: nginx-edge
          ttl: 3600
    proxy:
      enabled: true
      upstream_port: 8123
      upstream_host: docker-runtime
      public_fqdn: myservice.example.com
      auth_proxy: false
```

## Step 2: Create the Service Role

Create: `collections/ansible_collections/lv3/platform/roles/my_new_service_runtime/`

### Directory Structure
```
my_new_service_runtime/
├── README.md                          # Service description, architecture
├── defaults/main.yml                  # ONLY service-specific defaults
├── meta/argument_specs.yml            # ONLY service-specific variables
├── tasks/main.yml                     # Convergence tasks
├── tasks/verify.yml                   # Health checks (optional)
├── templates/
│   ├── docker-compose.yml.j2          # (docker_compose only)
│   └── environment.env.j2             # Runtime environment
└── handlers/main.yml                  # (optional)
```

### defaults/main.yml Template

```yaml
---
# Purpose: Define my_new_service runtime defaults (ADR 0373 — conventional variables are derived).
# Use case: Loaded whenever the my_new_service runtime converges or verifies.
# Inputs: Platform topology, OpenBao settings.
# Outputs: Supplies stable defaults for the my_new_service runtime role.
# Idempotency: Fully idempotent because this file only declares defaults.
# Dependencies: ADR 0165, ADR 0060, ADR 0373.
# NOTE: Conventional variables (site_dir, data_dir, secret_dir, compose_file, env_file,
# openbao_*, container_name, internal_port, local_artifact_dir) are derived
# from platform_service_registry — ADR 0373.

---
# Service-specific my_new_service configuration
my_new_service_runtime_option_1: value1
my_new_service_runtime_option_2: value2
my_new_service_runtime_database_host: "{{ hostvars['proxmox-host'].platform_guest_catalog.by_name['postgres-vm'].ipv4 }}"
```

**CRITICAL:** Do NOT define these — they are derived:
- `my_new_service_runtime_site_dir` (docker_compose)
- `my_new_service_runtime_data_dir` (all types)
- `my_new_service_runtime_secret_dir` (all types)
- `my_new_service_runtime_compose_file` (docker_compose)
- `my_new_service_runtime_env_file` (all types)
- `my_new_service_runtime_container_name` (docker_compose, infrastructure, multi_instance)
- `my_new_service_runtime_image` (docker_compose)
- `my_new_service_runtime_internal_port` (all types)
- `my_new_service_runtime_local_artifact_dir` (docker_compose)
- `my_new_service_runtime_openbao_*` (all types, if needs_openbao=true)

### tasks/main.yml Template

```yaml
---
- name: Derive conventional service variables from platform_service_registry
  ansible.builtin.import_tasks: ../common/tasks/derive_service_defaults.yml
  vars:
    common_derive_service_name: my_new_service

- name: Validate my_new_service runtime inputs
  ansible.builtin.assert:
    that:
      - my_new_service_runtime_option_1 | length > 0
      - my_new_service_runtime_database_host | length > 0
    fail_msg: "my_new_service_runtime requires option_1 and database_host"
    quiet: true

- name: Create my_new_service directories
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
    owner: root
    group: root
    mode: '0755'
  loop:
    - "{{ my_new_service_runtime_site_dir }}"
    - "{{ my_new_service_runtime_data_dir }}"

# ... rest of convergence tasks ...
```

### meta/argument_specs.yml Template

```yaml
---
argument_specs:
  main:
    short_description: Converge my_new_service on the platform.
    description: >-
      Converges my_new_service on docker-runtime.
      Conventional variables (site_dir, data_dir, secret_dir, compose_file, env_file,
      container_name, internal_port, openbao_*, local_artifact_dir) are automatically
      derived from the platform_service_registry via ADR 0373.
      Only service-specific variables are documented here.
    options:
      my_new_service_runtime_option_1:
        type: str
        required: true
        description:
          - Description of what option_1 does.
      my_new_service_runtime_database_host:
        type: str
        required: true
        description:
          - Host where the database is running.
```

## Step 3: Regenerate Cross-Cutting And Platform Facts

After updating `inventory/group_vars/platform_services.yml`, regenerate the derived ADR 0374 and platform-facts outputs:

```bash
make generate-cross-cutting-artifacts
make generate-platform-vars
```

This refreshes:

- `config/generated/dns-declarations.yaml`
- `config/generated/nginx-upstreams.yaml`
- `config/generated/sso-clients.yaml`
- `inventory/group_vars/platform_hairpin.yml`
- `inventory/group_vars/platform_tls_certs.yml`
- `inventory/group_vars/platform.yml`

Only update `scripts/generate_platform_vars.py` when the new service needs a brand-new derived fact shape that cannot already be expressed from the registry inputs.

## Step 4: Update Service Topology Consumers (if needed)

If the service needs to be discovered or referenced by other services beyond the standard registry-derived outputs, update:

- `scripts/generate_discovery_artifacts.py` → add to AGENTS.md or generated discovery surfaces
- any service-specific topology consumer that reads `platform.yml`

## Step 5: Create Convergence Playbook

Create: `collections/ansible_collections/lv3/platform/playbooks/my_new_service.yml`

```yaml
---
- name: Converge my_new_service on the platform
  hosts: docker-runtime
  become: true
  gather_facts: true
  tags: [tier-1, service-my_new_service]

  pre_tasks:
    - name: Run shared preflight checks
      ansible.builtin.import_tasks: tasks/preflight.yml

  roles:
    - role: lv3.platform.common
    - role: lv3.platform.docker_runtime
    - role: lv3.platform.my_new_service_runtime

  post_tasks:
    - name: Run shared completion notifications
      ansible.builtin.import_tasks: tasks/post-verify.yml
```

Create: `collections/ansible_collections/lv3/platform/playbooks/services/my_new_service.yml`

```yaml
---
- import_playbook: ../my_new_service.yml
```

The `playbooks/services/<service>.yml` wrapper is not optional. The governed
`make live-apply-service` and workflow-catalog contract expect this exact
wrapper/import pattern so the scoped runner can resolve the service entrypoint
without custom host expressions.

## Step 6: Add to Makefile (convenience)

Edit: `Makefile`

```makefile
converge-my_new_service:
	ansible-playbook -i inventory/ \
		collections/ansible_collections/lv3/platform/playbooks/services/my_new_service.yml \
		-e "playbook_execution_env=$(env)"
```

## Step 7: Add to Workstream (if significant)

If this is a multi-session feature, register it:

Edit: `workstreams/active/<id>.yaml`

```yaml
---
id: ws-XXXX
title: Add my_new_service to platform
owner: [your-agent-id]
phase: implementation
status: in_progress
assigned_to:
  - component: my_new_service_runtime role
    owner: [agent]
    status: in_progress
---
```

Then regenerate:
```bash
python3 scripts/workstream_registry.py --write
```

## Step 8: Verify and Test

1. **Validate service registry:**
   ```bash
   python scripts/validate_service_registry.py
   ```

2. **Validate generated cross-cutting outputs:**
   ```bash
   make validate-generated-cross-cutting
   make validate-generated-vars
   ```

3. **Run convergence:**
   ```bash
   make converge-my_new_service env=production
   ```

4. **Verify service:**
   ```bash
   # Check convergence logs
   # Check health endpoint: curl http://docker-runtime:8123/health
   # Check service is responding
   ```

## Step 9: Merge to main and Live-Apply

1. Create pull request on verify branch
2. Get approval (reference ADR 0373)
3. Merge to main:
   ```bash
   git checkout main && git merge verify --no-ff
   ```
4. Live-apply from the merged `main` tree:
   ```bash
   make converge-my_new_service env=production
   ```
5. Verify the real service surface (internal health plus public edge behavior if published).
6. Record a live-apply receipt under `receipts/live-applies/`.
7. Bump `VERSION` and cut the release artifacts on `main`.
8. Only after the merged-tree replay succeeds, bump `platform_version` in `versions/stack.yaml`.
9. Push `origin/main`.

## Service Type Decision Matrix

| Service Type | When to Use | Key Characteristics |
|---|---|---|
| **docker_compose** | Most application services | Runs in Docker, has site_dir, uses docker-compose.yml, derives image from catalog |
| **system_package** | Debian/system packages | Installed via apt, uses /etc/* and /var/lib/*, no Docker image, state_dirs required |
| **infrastructure** | Core platform services | Docker daemon, kernel modules, minimal derivation, service-specific patterns |
| **multi_instance** | Multi-tenant or multi-replica patterns | Has custom instance dict (e.g., neko_instances), minimal standard derivation |

## Extensibility for Future Use Cases

The ADR 0373 pattern is **designed to be extended**:

### Adding New Service Type
1. Update `platform_services.yml` header comments (lines 10-24)
2. Add new `service_type` value to derive_service_defaults.yml conditional blocks
3. Document derived variables for the new type
4. Add test in validate_service_registry.py

### Adding New Derived Variable
1. Add to derive_service_defaults.yml in the appropriate service_type block
2. Update template in all affected roles
3. Update argument_specs.yml in affected roles
4. Document in README.md

### Adding Custom Derivation Logic
Use `extra_defaults` in registry to compute service-specific values:

```yaml
my_complex_service:
  service_type: docker_compose
  extra_defaults:
    my_service_runtime_computed_value: "{{ derived_value | some_filter }}"
    my_service_runtime_port: "{{ platform_port_assignments.custom_port }}"
```

## Troubleshooting

**Problem:** Role fails with "variable X not found"
**Solution:** Check that X is being derived by derive_service_defaults.yml for your service_type

**Problem:** Derived variable has wrong value
**Solution:** Check registry entry in platform_services.yml — verify site_dir, state_dirs, extra_defaults

**Problem:** Service won't start — permission errors
**Solution:** Ensure derive_service_defaults is imported BEFORE tasks that use derived variables

---

**Reference:** ADR 0373, ADR 0374, AGENTS.md
**Last Updated:** 2026-04-09
**Maintainer:** Platform Architecture Team
