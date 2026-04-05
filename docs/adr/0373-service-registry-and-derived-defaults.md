# ADR 0373: Service Registry and Derived Defaults

- **Date**: 2026-04-06
- **Status**: Proposed
- **Deciders**: platform team
- **Concern**: platform, dry
- **Tags**: ansible, registry, defaults, dry, service-catalog

## Context

The platform manages ~50 runtime services. Each service defines **the same set of conventional variables** in its `defaults/main.yml` and validates them in `meta/argument_specs.yml`. A typical runtime role has 15-25 variables that follow strict naming conventions:

```yaml
# roles/directus_runtime/defaults/main.yml (representative excerpt)
directus_site_dir: /opt/directus
directus_data_dir: "{{ directus_site_dir }}/data"
directus_secret_dir: /etc/lv3/directus
directus_compose_file: "{{ directus_site_dir }}/docker-compose.yml"
directus_env_file: "{{ compose_runtime_secret_root }}/directus/runtime.env"
directus_legacy_env_file: "{{ directus_site_dir }}/directus.env"
directus_openbao_agent_dir: "{{ directus_site_dir }}/openbao"
directus_openbao_agent_image: "{{ openbao_agent_image }}"
directus_openbao_agent_container_name: directus-openbao-agent
directus_openbao_secret_path: services/directus/runtime-env
directus_openbao_policy_name: lv3-service-directus-runtime
directus_openbao_approle_name: directus-runtime
directus_container_name: directus
directus_image: "{{ container_image_catalog.images.directus_runtime.ref }}"
directus_local_artifact_dir: /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/directus
```

This pattern repeats identically across all ~50 runtime roles — **646+ lines** of variable definitions that differ only in the service name prefix. Additionally, **284+ lines** of identical argument spec definitions validate these same variables.

### The problem

1. **Convention violations are silent.** If a new role misspells `_secret_dir` as `_secrets_dir`, nothing catches it until runtime.
2. **Changing the convention requires editing 50 files.** Moving from `/opt/<service>` to `/srv/<service>` would require updating every role's defaults.
3. **Argument specs are pure boilerplate.** Every role validates `type: path, required: true` for the same set of conventional paths.
4. **The OpenBao variable block** (6 variables) is copied into 35+ roles with zero variation.

### Prior art: `platform_postgres_clients` (ADR 0359)

ADR 0359 successfully demonstrated this pattern for PostgreSQL: instead of 30 independent `{service}_postgres` roles each defining their own credentials, a single `platform_postgres_clients` registry declares all database relationships. The same approach applies here at a broader scope.

## Decision

Create a **platform service registry** in `inventory/group_vars/platform_services.yml` that declares each service's identity and metadata. A shared Ansible vars plugin (or `set_fact` task) derives all conventional variables from the registry, eliminating the need for each role to define them independently.

### Registry file

```
inventory/group_vars/platform_services.yml
```

### Registry format

```yaml
---
platform_service_registry:
  directus:
    # === Required fields ===
    image_catalog_key: directus_runtime        # Key in container_image_catalog.images
    internal_port: 8055
    host_group: docker-runtime-lv3             # Ansible host/group this service runs on

    # === Optional fields (defaults shown) ===
    site_dir: /opt/directus                    # Default: /opt/{{ service_name }}
    secret_dir: /etc/lv3/directus              # Default: /etc/lv3/{{ service_name }}
    container_name: directus                   # Default: {{ service_name }}
    needs_openbao: true                        # Default: true
    needs_redis: false                         # Default: false
    needs_postgres: true                       # Default: false
    local_artifact_dir: .local/directus        # Default: .local/{{ service_name }}

    # === Service-specific overrides (not conventional) ===
    extra_defaults:
      directus_admin_email: admin@lv3.org
      directus_health_path: /server/health
      directus_ping_path: /server/ping

  flagsmith:
    image_catalog_key: flagsmith_runtime
    internal_port: 8000
    host_group: docker-runtime-lv3
    needs_openbao: true
    needs_redis: false
    needs_postgres: true
    extra_defaults:
      flagsmith_health_path: /health

  gitea:
    image_catalog_key: gitea_runtime
    internal_port: 3000
    host_group: docker-runtime-lv3
    needs_openbao: true
    needs_redis: false
    needs_postgres: true

  # ... one entry per service
```

### Derived variables

For each service `S` in `platform_service_registry`, the following variables are **automatically derived** and set as Ansible facts. Roles should **not** define these in their `defaults/main.yml` — they are computed at runtime.

| Derived variable | Formula | Example (directus) |
|---|---|---|
| `{S}_site_dir` | `registry[S].site_dir \| default('/opt/' + S)` | `/opt/directus` |
| `{S}_data_dir` | `{S}_site_dir + '/data'` | `/opt/directus/data` |
| `{S}_secret_dir` | `registry[S].secret_dir \| default('/etc/lv3/' + S)` | `/etc/lv3/directus` |
| `{S}_compose_file` | `{S}_site_dir + '/docker-compose.yml'` | `/opt/directus/docker-compose.yml` |
| `{S}_env_file` | `compose_runtime_secret_root + '/' + S + '/runtime.env'` | `/run/secrets/directus/runtime.env` |
| `{S}_legacy_env_file` | `{S}_site_dir + '/' + S + '.env'` | `/opt/directus/directus.env` |
| `{S}_container_name` | `registry[S].container_name \| default(S)` | `directus` |
| `{S}_image` | `container_image_catalog.images[registry[S].image_catalog_key].ref` | `directus/directus:11.5.0` |
| `{S}_internal_port` | `registry[S].internal_port` | `8055` |
| `{S}_internal_base_url` | `'http://127.0.0.1:' + str(registry[S].internal_port)` | `http://127.0.0.1:8055` |
| `{S}_openbao_agent_dir` | `{S}_site_dir + '/openbao'` | `/opt/directus/openbao` |
| `{S}_openbao_agent_image` | `openbao_agent_image` (global) | `quay.io/openbao/openbao:2.2.0` |
| `{S}_openbao_agent_container_name` | `S + '-openbao-agent'` | `directus-openbao-agent` |
| `{S}_openbao_secret_path` | `'services/' + S + '/runtime-env'` | `services/directus/runtime-env` |
| `{S}_openbao_policy_name` | `'lv3-service-' + S + '-runtime'` | `lv3-service-directus-runtime` |
| `{S}_openbao_approle_name` | `S + '-runtime'` | `directus-runtime` |
| `{S}_local_artifact_dir` | `repo_root + '/' + registry[S].local_artifact_dir \| default('.local/' + S)` | `/path/to/repo/.local/directus` |

Plus all `extra_defaults` key-value pairs are set as-is.

### Implementation mechanism: shared task `derive_service_defaults.yml`

Create `common/tasks/derive_service_defaults.yml`:

**Input variables:**
```yaml
common_derive_service_name: "directus"   # Must match a key in platform_service_registry
```

**Exact implementation:**

```yaml
---
- name: "Validate {{ common_derive_service_name }} exists in platform_service_registry"
  ansible.builtin.assert:
    that:
      - common_derive_service_name in platform_service_registry
    fail_msg: >-
      Service '{{ common_derive_service_name }}' not found in platform_service_registry.
      Add it to inventory/group_vars/platform_services.yml.
    quiet: true

- name: "Derive conventional defaults for {{ common_derive_service_name }}"
  ansible.builtin.set_fact:
    "{{ common_derive_service_name }}_site_dir": >-
      {{ platform_service_registry[common_derive_service_name].site_dir
         | default('/opt/' + common_derive_service_name) }}
    "{{ common_derive_service_name }}_data_dir": >-
      {{ (platform_service_registry[common_derive_service_name].site_dir
          | default('/opt/' + common_derive_service_name)) + '/data' }}
    "{{ common_derive_service_name }}_secret_dir": >-
      {{ platform_service_registry[common_derive_service_name].secret_dir
         | default('/etc/lv3/' + common_derive_service_name) }}
    "{{ common_derive_service_name }}_compose_file": >-
      {{ (platform_service_registry[common_derive_service_name].site_dir
          | default('/opt/' + common_derive_service_name)) + '/docker-compose.yml' }}
    "{{ common_derive_service_name }}_env_file": >-
      {{ compose_runtime_secret_root + '/' + common_derive_service_name + '/runtime.env' }}
    "{{ common_derive_service_name }}_legacy_env_file": >-
      {{ (platform_service_registry[common_derive_service_name].site_dir
          | default('/opt/' + common_derive_service_name)) + '/' + common_derive_service_name + '.env' }}
    "{{ common_derive_service_name }}_container_name": >-
      {{ platform_service_registry[common_derive_service_name].container_name
         | default(common_derive_service_name) }}
    "{{ common_derive_service_name }}_image": >-
      {{ container_image_catalog.images[platform_service_registry[common_derive_service_name].image_catalog_key].ref }}
    "{{ common_derive_service_name }}_internal_port": >-
      {{ platform_service_registry[common_derive_service_name].internal_port }}
    "{{ common_derive_service_name }}_internal_base_url": >-
      {{ 'http://127.0.0.1:' + (platform_service_registry[common_derive_service_name].internal_port | string) }}
    "{{ common_derive_service_name }}_local_artifact_dir": >-
      {{ platform_local_artifact_base + '/' + (platform_service_registry[common_derive_service_name].local_artifact_dir
         | default(common_derive_service_name)) }}

- name: "Derive OpenBao defaults for {{ common_derive_service_name }}"
  ansible.builtin.set_fact:
    "{{ common_derive_service_name }}_openbao_agent_dir": >-
      {{ (platform_service_registry[common_derive_service_name].site_dir
          | default('/opt/' + common_derive_service_name)) + '/openbao' }}
    "{{ common_derive_service_name }}_openbao_agent_image": "{{ openbao_agent_image }}"
    "{{ common_derive_service_name }}_openbao_agent_container_name": >-
      {{ common_derive_service_name }}-openbao-agent
    "{{ common_derive_service_name }}_openbao_secret_path": >-
      services/{{ common_derive_service_name }}/runtime-env
    "{{ common_derive_service_name }}_openbao_policy_name": >-
      lv3-service-{{ common_derive_service_name }}-runtime
    "{{ common_derive_service_name }}_openbao_approle_name": >-
      {{ common_derive_service_name }}-runtime
  when: platform_service_registry[common_derive_service_name].needs_openbao | default(true)

- name: "Apply extra defaults for {{ common_derive_service_name }}"
  ansible.builtin.set_fact:
    "{{ item.key }}": "{{ item.value }}"
  loop: "{{ platform_service_registry[common_derive_service_name].extra_defaults | default({}) | dict2items }}"
  loop_control:
    label: "{{ item.key }}"
```

### How a runtime role uses it

At the top of its `tasks/main.yml`, before any other task:

```yaml
---
- name: Derive Directus conventional defaults from the service registry
  ansible.builtin.include_role:
    name: lv3.platform.common
    tasks_from: derive_service_defaults
  vars:
    common_derive_service_name: directus

# ... rest of the role's tasks, which can now use {{ directus_site_dir }}, {{ directus_image }}, etc.
```

### What happens to `defaults/main.yml`

After migration, a role's `defaults/main.yml` contains **only** service-specific defaults that are NOT derivable from the registry:

```yaml
# roles/directus_runtime/defaults/main.yml — AFTER migration
# Conventional defaults (site_dir, image, container_name, openbao_*, etc.)
# are derived from platform_service_registry by common/tasks/derive_service_defaults.
# Only non-conventional, service-specific defaults remain here.

directus_admin_email: admin@lv3.org
directus_health_path: /server/health
directus_ping_path: /server/ping
directus_openapi_path: /server/specs/oas
directus_bootstrap_collection_name: platform_registry
directus_bootstrap_public_hostname: data.lv3.org
directus_bootstrap_internal_url: "http://127.0.0.1:8055"
```

### What happens to `meta/argument_specs.yml`

The conventional variables are removed from argument specs since they're guaranteed by the derivation task. Only service-specific variables remain:

```yaml
# roles/directus_runtime/meta/argument_specs.yml — AFTER migration
argument_specs:
  main:
    options:
      directus_admin_email:
        type: str
        required: true
      directus_health_path:
        type: str
        required: true
      # ... only non-derived variables
```

### Validation script

Create `scripts/validate_service_registry.py` that:

1. Loads `inventory/group_vars/platform_services.yml`
2. Validates each entry has required fields (`image_catalog_key`, `internal_port`, `host_group`)
3. Validates `image_catalog_key` exists in the container image catalog
4. Validates `host_group` exists in the Ansible inventory
5. Checks for duplicate service names
6. Checks that every `*_runtime` role has a corresponding registry entry (and warns if not)

This script runs in the `schema-validation` gate lane.

```bash
# Run validation:
python scripts/validate_service_registry.py --check

# List all registered services:
python scripts/validate_service_registry.py --list
```

### Migration procedure

#### Phase 1: Create the registry and derivation task (no behavioural change)

1. Create `inventory/group_vars/platform_services.yml` with entries for all ~50 services
2. Create `common/tasks/derive_service_defaults.yml`
3. Create `scripts/validate_service_registry.py`
4. Run the validation script to verify registry completeness
5. Commit

#### Phase 2: Migrate `directus_runtime` as reference (1 commit)

1. Add `include_role: common/derive_service_defaults` at the top of `directus_runtime/tasks/main.yml`
2. Remove all conventional variables from `directus_runtime/defaults/main.yml`
3. Remove conventional entries from `directus_runtime/meta/argument_specs.yml`
4. Run `ansible-playbook playbooks/directus.yml --check -vvv` and verify all variables resolve correctly
5. Compare the effective variable values before and after migration

#### Phase 3: Migrate remaining roles in batches of 5-8

For each role:
1. Add the derive include
2. Remove conventional defaults
3. Trim argument specs
4. Verify with `--check`

#### Rollback strategy

If a role's migration breaks, the fix is to temporarily re-add the removed defaults. The derivation task uses `set_fact`, which has higher precedence than `defaults/` — so having both is safe (the derived value wins). This means migration can be done incrementally with no risk.

### What NOT to do

- Do **not** remove `defaults/main.yml` files entirely. They still hold service-specific defaults.
- Do **not** use a custom Ansible vars plugin. `set_fact` via `include_role` is simpler, debuggable, and doesn't require plugin installation. A vars plugin can be considered later as an optimization.
- Do **not** rename existing variables. The derived variables use the exact same names as today's defaults — `directus_site_dir`, `directus_image`, etc. This ensures zero breakage of templates and tasks that reference them.
- Do **not** add optional fields to the registry just because they might be useful someday. Start with the minimum required fields and add more only when a concrete use case demands it.
- Do **not** generate Jinja2 templates from the registry. Templates continue to use `{{ directus_site_dir }}` etc. — the only change is where that variable gets its value.

## Consequences

**Positive:**
- Eliminates ~646 lines of duplicated variable definitions across 50 defaults files.
- Eliminates ~284 lines of duplicated argument specs across 50 roles.
- Convention changes (e.g., moving site_dir from `/opt/` to `/srv/`) require editing one task file instead of 50 defaults files.
- New services declare their identity once in the registry; all conventional variables are derived automatically.
- The registry serves as a single-page catalog of all platform services, their images, ports, and hosts.

**Negative / Trade-offs:**
- `set_fact` runs at play time, not at variable-load time. This means the derivation task must be included at the top of each role's task list. If a developer forgets this include, the variables will be undefined.
- The registry is yet another YAML file that must be kept in sync with reality. Mitigated by the validation script.
- Variable precedence: `set_fact` overrides `defaults/` but is overridden by `vars/` and `-e`. This is the desired behaviour but could confuse developers unfamiliar with Ansible precedence.

## Implementation plan

1. Create `inventory/group_vars/platform_services.yml` with all service entries
2. Create `common/tasks/derive_service_defaults.yml`
3. Create `scripts/validate_service_registry.py`
4. Migrate `directus_runtime` as reference
5. Migrate remaining roles in batches
6. Remove redundant conventional variables from each migrated role's `defaults/main.yml`
7. Trim `argument_specs.yml` for each migrated role

## Depends on

- ADR 0359 (Declarative PostgreSQL Client Registry) — established the "declare once, derive everywhere" pattern
- ADR 0344 (Single-Source Environment Topology) — `platform_guest_catalog` for host IP resolution

## Related

- ADR 0368 (Compose Macro Library) — macros use derived variables like `{{ directus_openbao_agent_image }}`
- ADR 0370 (Service Lifecycle Task Includes) — shared tasks use derived variables
- ADR 0374 (Cross-Cutting Service Manifest) — extends this registry with DNS, SSO, certs, proxy declarations
