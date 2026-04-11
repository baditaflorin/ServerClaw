# DRY Centralization — Downstream Implementation Prompts

These prompts are designed to be passed to a downstream model (e.g., ChatGPT Codex, Claude Sonnet) one at a time, in order. Each prompt is self-contained and references the specific ADR that governs the implementation.

**Implementation order matters.** ADR 0369 has zero dependencies; ADR 0374 depends on everything before it. Do not skip or reorder.

---

## Prompt 1: ADR 0369 — Python Validation Toolkit

```
You are implementing ADR 0369 from this repository. Read `docs/adr/0369-python-validation-toolkit.md` completely before writing any code. Follow it exactly — do not deviate from the function signatures, error message formats, or migration procedure described in the ADR.

## Your task

1. Create `scripts/validation_toolkit.py` with the exact functions specified in the ADR. Copy the function signatures and implementations verbatim from the ADR's "Module contents" section. Do not add extra functions, do not rename parameters, do not change error message formats.

2. Create `scripts/test_validation_toolkit.py` — a simple test script that exercises each function with both valid and invalid inputs. Use plain `assert` statements, not unittest or pytest (to avoid adding dependencies). The test script must be runnable with `python scripts/test_validation_toolkit.py` with zero dependencies.

3. Migrate the validation scripts one at a time. Run this command first to find all scripts that define their own validators:
   ```
   grep -rl "def require_mapping\|def require_str\|def require_list" scripts/ --include="*.py"
   ```

4. For EACH script found:
   a. Open the script and identify all locally defined `require_*` functions
   b. Delete the local function definitions
   c. Add `from validation_toolkit import require_str, require_mapping, require_list, ...` (only the functions actually used)
   d. Ensure the script has a `sys.path.insert(0, str(Path(__file__).resolve().parent))` line (or equivalent) so the import resolves correctly
   e. Run the script's own validation mode to verify it still works (most scripts support `--check` or have a `if __name__ == "__main__"` block)
   f. Commit the single script migration: `git add scripts/validation_toolkit.py scripts/<script_name>.py && git commit -m "refactor(<script_name>): use shared validation_toolkit — ADR 0369"`

5. After ALL scripts are migrated, run `make validate-schemas` to verify the full gate passes.

## Rules you must follow

- Do NOT move validation_toolkit.py into a package with __init__.py. Keep it flat in scripts/.
- Do NOT add dependencies beyond Python stdlib. The module must work in the Docker validation container.
- Do NOT change the error message format "{path} must be ...". The gate log parsers grep for this.
- Do NOT create a class hierarchy. These are plain functions.
- Do NOT batch multiple script migrations into one commit. One script per commit.
- Before writing any code, read `AGENTS.md` and `CLAUDE.md` at the repo root for working rules.
- This is a branch-local change. Do NOT modify VERSION, changelog.md, RELEASE.md, or README.md.
```

---

## Prompt 2: ADR 0368 — Docker Compose Jinja2 Macro Library

```
You are implementing ADR 0368 from this repository. Read `docs/adr/0368-docker-compose-jinja2-macro-library.md` completely before writing any code. Follow it exactly.

## Your task

### Step 1: Create the macro library

Create `collections/ansible_collections/lv3/platform/roles/common/templates/compose_macros.j2` with the 6 macros specified in the ADR:

1. `openbao_sidecar(prefix)` — emits the OpenBao agent sidecar service block
2. `redis_service(prefix, requirepass=true, use_valkey=false, append_only=true)` — emits a Redis service
3. `healthcheck(type, port, path="/", interval=10, timeout=5, retries=12, start_period=None)` — emits a healthcheck block
4. `logging(max_size="10m", max_file="3")` — emits the logging configuration
5. `service_network()` — emits the platform service network definition
6. `hairpin_hosts()` — emits extra_hosts from `platform_hairpin_nat_hosts`

Copy the macro implementations from the ADR. Use `vars[prefix + '_...']` for dynamic variable access (NOT `hostvars[inventory_hostname]`).

### Step 2: Create the hairpin NAT variable

Add `platform_hairpin_nat_hosts` to `inventory/group_vars/platform.yml`. To populate it:

1. Run: `grep -r "extra_hosts" collections/ansible_collections/lv3/platform/roles/*/templates/docker-compose.yml.j2`
2. Collect all hostname:address pairs found across all compose templates
3. Deduplicate and sort them into the variable

### Step 3: Migrate directus_runtime as reference implementation

Edit `collections/ansible_collections/lv3/platform/roles/directus_runtime/templates/docker-compose.yml.j2`:

1. Add the import line at the very top: `{% from 'compose_macros.j2' import openbao_sidecar, redis_service, healthcheck, logging, service_network, hairpin_hosts %}`
2. Replace the inline openbao-agent service block with `{{ openbao_sidecar("directus") }}`
3. Replace inline `logging:` blocks with `{{ logging() }}`
4. Replace the inline `networks:` block at the bottom with `{{ service_network() }}`
5. If the file has `extra_hosts`, replace with `{{ hairpin_hosts() }}`

### Step 4: Verify

After modifying the directus template, verify it renders correctly:
```
ansible -m template -a "src=collections/ansible_collections/lv3/platform/roles/directus_runtime/templates/docker-compose.yml.j2 dest=/tmp/directus-compose-test.yml" localhost --extra-vars @inventory/group_vars/platform.yml
```

If the template search path doesn't resolve `compose_macros.j2`, add this to `directus_runtime/defaults/main.yml`:
```yaml
directus_template_search_path:
  - "{{ role_path }}/templates"
  - "{{ role_path }}/../../common/templates"
```

### Step 5: Migrate remaining roles

After directus works, migrate the other 34 roles that use the openbao sidecar pattern. Find them with:
```
grep -rl "openbao-agent:" collections/ansible_collections/lv3/platform/roles/*/templates/docker-compose.yml.j2
```

For each role: add the import line, replace the sidecar block, replace logging blocks, replace network blocks. Commit in batches of 5-8 roles.

## Rules you must follow

- Do NOT modify the macro output to differ from what the ADR specifies.
- Do NOT change any service's actual compose behaviour — the rendered output must be functionally identical.
- Do NOT use symlinks. Use the template search path approach.
- Before writing any code, read `AGENTS.md` and `CLAUDE.md` at the repo root.
- Run `make validate-yaml` after each batch of migrations.
- This is a branch-local change. Do NOT modify VERSION, changelog.md, RELEASE.md, or README.md.
```

---

## Prompt 3: ADR 0371 — Parameterized Service Verification Tasks

```
You are implementing ADR 0371 from this repository. Read `docs/adr/0371-parameterized-verify-tasks.md` completely before writing any code. Follow it exactly.

## Your task

### Step 1: Create the shared verification task files

Create these two files:
- `collections/ansible_collections/lv3/platform/roles/common/tasks/verify_service_health.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/verify_service_health_extra.yml`

Copy the implementations verbatim from the ADR.

### Step 2: Add default values

Edit `collections/ansible_collections/lv3/platform/roles/common/defaults/main.yml` and add default values for all `common_verify_*` variables documented in the ADR. Set sensible defaults:
```yaml
common_verify_port_host: "127.0.0.1"
common_verify_port_timeout: 300
common_verify_health_url: ""
common_verify_health_retries: 36
common_verify_health_delay: 5
common_verify_health_status_code: 200
common_verify_health_assertions: []
common_verify_health_assertion_msg: ""
common_verify_extra_endpoints: []
```

### Step 3: Migrate directus_runtime/tasks/verify.yml as reference

Read the current `collections/ansible_collections/lv3/platform/roles/directus_runtime/tasks/verify.yml` to understand what it does (port wait + health + ping + OpenAPI). Then rewrite it as a thin wrapper:

```yaml
---
- name: Verify the Directus runtime
  ansible.builtin.include_role:
    name: lv3.platform.common
    tasks_from: verify_service_health
  vars:
    common_verify_service_name: directus
    common_verify_port: "{{ directus_internal_port }}"
    common_verify_health_url: "{{ directus_internal_base_url }}{{ directus_health_path }}"
    common_verify_health_assertions:
      - "common_verify_health_response.json.status == 'ok'"
    common_verify_health_assertion_msg: "Directus /server/health did not report status=ok."
    common_verify_extra_endpoints:
      - url: "{{ directus_internal_base_url }}{{ directus_ping_path }}"
        assertions:
          - "common_verify_extra_response.content | trim == 'pong'"
        assertion_msg: "Directus /server/ping did not return pong."
      - url: "{{ directus_internal_base_url }}{{ directus_openapi_path }}"
        assertions:
          - "'paths' in common_verify_extra_response.json"
        assertion_msg: "Directus OpenAPI document did not parse correctly."
```

### Step 4: Migrate simple roles

Find all verify.yml files: `find collections/ansible_collections/lv3/platform/roles -name verify.yml -path "*/tasks/*"`

Read each one. For roles that only do port wait + HTTP health check (no custom logic), rewrite as a thin wrapper. Start with the simplest ones: semaphore, dozzle, portainer, typesense.

### Step 5: Migrate remaining roles

Work through medium and complex roles. For roles with custom verification logic (e.g., database checks, bootstrap scripts), KEEP the custom tasks and add the shared include BEFORE them.

## Rules you must follow

- Do NOT delete verify.yml files from individual roles. They remain as thin wrappers.
- Do NOT change retry/delay values during migration. Match the existing values exactly. Standardize in a follow-up.
- Do NOT add container-running checks (docker ps) to the shared task.
- Run `make validate-ansible-syntax` after each batch.
- Read `AGENTS.md` and `CLAUDE.md` at the repo root before starting.
- This is a branch-local change. Do NOT modify VERSION, changelog.md, RELEASE.md, or README.md.
```

---

## Prompt 4: ADR 0370 — Service Lifecycle Task Includes

```
You are implementing ADR 0370 from this repository. Read `docs/adr/0370-service-lifecycle-task-includes.md` completely before writing any code. Follow it exactly.

## Prerequisites

ADR 0371 (verify tasks) should be implemented first. If it hasn't been done yet, do it before starting this one.

## Your task

### Step 1: Create the shared task files

Create these files in `collections/ansible_collections/lv3/platform/roles/common/tasks/`:

1. `check_local_secrets.yml` — checks that secret files exist on the control machine before deploying
2. `manage_service_secrets.yml` — generates, reads, and mirrors secrets between remote host and control machine
3. `docker_compose_converge.yml` — pulls images, recovers Docker networking, starts compose stack with drift detection

Copy the implementations verbatim from the ADR. Each file has its exact implementation listed in the ADR.

### Step 2: Add default values

Edit `collections/ansible_collections/lv3/platform/roles/common/defaults/main.yml` and add default values for all `common_check_local_secrets_*`, `common_manage_service_secrets_*`, and `common_docker_compose_converge_*` variables.

### Step 3: Migrate directus_runtime as reference

Read the current `collections/ansible_collections/lv3/platform/roles/directus_runtime/tasks/main.yml` (411 lines). Map each section to the shared includes:

- Lines 8-28 (input validation): Already handled by `common/tasks/assert_vars.yml`. Use `include_role: common, tasks_from: assert_vars` with the appropriate variable list.
- Lines 30-70 (check secrets): Replace with `include_role: common, tasks_from: check_local_secrets`. Map the 3 secret files (database password, keycloak secret, service token) into `common_check_local_secrets_files`.
- Lines 81-92 (directories): Already uses or should use `common/tasks/directory_tree.yml`.
- Lines 94-162 (generate + read + mirror secrets): Replace with `include_role: common, tasks_from: manage_service_secrets`. Map the generate/read/mirror lists as shown in the ADR.
- Lines 164-197 (OpenBao): Already extracted — no change needed.
- Lines 199-216 (template rendering): Keep as-is — this is service-specific.
- Lines 218-373 (pull + NAT recovery + compose up): Replace with `include_role: common, tasks_from: docker_compose_converge`.
- Lines 375-411 (verify + bootstrap): Keep as-is — service-specific.

After migration, `directus_runtime/tasks/main.yml` should be ~100-120 lines instead of 411.

### Step 4: Verify identical behaviour

```bash
# Run --check with verbose output before and after:
ansible-playbook playbooks/directus.yml -e env=production -l docker-runtime --check -vvv 2>&1 | tee /tmp/before.log
# (apply migration)
ansible-playbook playbooks/directus.yml -e env=production -l docker-runtime --check -vvv 2>&1 | tee /tmp/after.log
# Compare task names and actions:
diff <(grep '^TASK' /tmp/before.log) <(grep '^TASK' /tmp/after.log)
```

### Step 5: Migrate remaining roles in batches

Group by complexity (the ADR specifies exact batches):
- Batch A (simplest): outline, semaphore, grist, langfuse, label_studio
- Batch B (extra secrets): gitea, keycloak, nextcloud, mattermost, n8n
- Batch C (complex stacks): dify, plane, superset, windmill, temporal
- Batch D: all remaining *_runtime roles

After each batch: `make validate-yaml && make validate-ansible-syntax`

### Important: What to keep in each role

After migration, each `*_runtime/tasks/main.yml` still contains:
- The `include_role` calls to the shared task files (with service-specific variable mappings)
- Template rendering tasks (service-specific templates)
- OpenBao setup (already extracted, just the include call)
- Any service-specific bootstrap or post-deploy tasks
- The `import_tasks: verify.yml` call

The role does NOT become empty. It becomes a shorter orchestration file that calls shared includes in the correct order.

## Rules you must follow

- Do NOT create a mega-role that replaces all runtime roles.
- Do NOT force all roles to use all three includes — skip includes that don't apply (e.g., dozzle_runtime doesn't generate secrets).
- Do NOT change the variable naming convention (<service>_*). Shared includes use common_* namespace.
- Do NOT remove service-specific tasks/main.yml files.
- Read `AGENTS.md` and `CLAUDE.md` at the repo root before starting.
- This is a branch-local change. Do NOT modify VERSION, changelog.md, RELEASE.md, or README.md.
```

---

## Prompt 5: ADR 0372 — Data-Driven Playbook Composition

```
You are implementing ADR 0372 from this repository. Read `docs/adr/0372-data-driven-playbook-composition.md` completely before writing any code. Follow it exactly.

## Prerequisites

ADR 0370 (lifecycle task includes) should be implemented first.

## Your task

### Step 1: Create the _includes directory and shared playbook files

Create `collections/ansible_collections/lv3/platform/playbooks/_includes/` and add these 4 files:

1. `dns_publication.yml` — the 58-line DNS play, parameterized by `service_dns_fqdn`
2. `postgres_preparation.yml` — parameterized by `service_postgres_role`
3. `docker_runtime_converge.yml` — parameterized by `service_runtime_roles` (list) and `service_audit_name`
4. `nginx_edge_publication.yml` — parameterized by `service_audit_name`

Copy implementations from the ADR. Pay special attention to the `playbook_dir` relative paths — the `_includes/` files are inside the `playbooks/` directory, so relative paths to `config/`, `inventory/`, and `tasks/` remain the same.

### Step 2: Create the vars directory and directus descriptor

Create `collections/ansible_collections/lv3/platform/playbooks/vars/directus.yml`:
```yaml
---
service_audit_name: directus
service_dns_fqdn: data.example.com
service_postgres_role: lv3.platform.directus_postgres
service_runtime_roles:
  - lv3.platform.docker_runtime
  - lv3.platform.keycloak_runtime
  - lv3.platform.directus_runtime
service_needs_dns: true
service_needs_postgres: true
service_needs_nginx_edge: true
```

### Step 3: Migrate directus.yml

Read the current `collections/ansible_collections/lv3/platform/playbooks/directus.yml` (176 lines). Rewrite it to use `import_playbook` calls to the shared includes for the standard plays, keeping only the Directus-specific plays (access model seed, public verification) inline.

The ADR shows the exact target structure. The migrated file should be significantly shorter.

**Critical Ansible detail:** `import_playbook` does not support `vars:`. Variables must be passed via `-e @playbooks/vars/directus.yml` on the command line. Update the Makefile `converge-directus` target accordingly.

### Step 4: Create vars files for remaining services

Read each existing playbook in `playbooks/`. For each, create a `playbooks/vars/<service>.yml` descriptor. You need to extract:
- `service_dns_fqdn` — from the DNS publication play's `subdomain_fqdn` variable
- `service_postgres_role` — from the PostgreSQL play's `roles:` list
- `service_runtime_roles` — from the Docker runtime play's `roles:` list (in order)
- `service_needs_*` flags — based on which plays exist in the playbook

### Step 5: Migrate remaining playbooks

For each playbook:
1. Create its `vars/<service>.yml` descriptor
2. Rewrite the playbook to use `import_playbook` for standard plays
3. Keep any service-specific plays inline
4. Update the corresponding Makefile target to pass `-e @playbooks/vars/<service>.yml`

Work in batches:
- Batch 1 (full standard stack): flagsmith, glitchtip, label-studio, lago, n8n, nextcloud, superset, plausible
- Batch 2 (docker + nginx): headscale, ntfy, dozzle, livekit
- Batch 3 (docker only): ollama, open-webui, searxng
- Batch 4: remaining playbooks

### Step 6: Verify

After each batch:
```bash
# Verify task listing matches:
ansible-playbook playbooks/<service>.yml -e @playbooks/vars/<service>.yml -e env=production --list-tasks
# Verify check mode passes:
ansible-playbook playbooks/<service>.yml -e @playbooks/vars/<service>.yml -e env=production --check
```

## Rules you must follow

- Do NOT delete per-service playbook files. They remain as orchestration entry points.
- Do NOT create a single meta-playbook that deploys all services.
- Do NOT use `ansible.builtin.include_playbook` (it doesn't exist) — use `import_playbook`.
- Do NOT put service-specific plays into the shared includes.
- Do NOT change playbook_dir-relative paths in the includes.
- Read `AGENTS.md` and `CLAUDE.md` at the repo root before starting.
- This is a branch-local change. Do NOT modify VERSION, changelog.md, RELEASE.md, or README.md.
```

---

## Prompt 6: ADR 0373 — Service Registry and Derived Defaults

```
You are implementing ADR 0373 from this repository. Read `docs/adr/0373-service-registry-and-derived-defaults.md` completely before writing any code. Follow it exactly.

## Prerequisites

ADR 0370 (lifecycle task includes) should be implemented first. ADR 0369 (validation toolkit) is needed for the validation script.

## Your task

### Step 1: Create the service registry

Create `inventory/group_vars/platform_services.yml` with entries for all runtime services. To build the registry:

1. List all runtime roles: `ls collections/ansible_collections/lv3/platform/roles/*_runtime/`
2. For each role, read its `defaults/main.yml` to extract: image_catalog_key, internal_port, host_group
3. Populate the registry entry with these values plus any overrides

The ADR shows the exact format. Every runtime role must have a corresponding registry entry.

### Step 2: Create the derivation task

Create `collections/ansible_collections/lv3/platform/roles/common/tasks/derive_service_defaults.yml` with the exact implementation from the ADR. This task:
- Validates the service exists in `platform_service_registry`
- Derives all conventional variables (site_dir, data_dir, secret_dir, compose_file, env_file, image, container_name, openbao_*, etc.)
- Applies extra_defaults as additional facts

### Step 3: Create the validation script

Create `scripts/validate_service_registry.py` that:
1. Loads `inventory/group_vars/platform_services.yml`
2. Validates required fields per entry (image_catalog_key, internal_port, host_group)
3. Cross-references image_catalog_key against the container image catalog
4. Warns about *_runtime roles that have no registry entry

Use `from validation_toolkit import require_str, require_mapping, require_int` (from ADR 0369).

The script must support:
- `python scripts/validate_service_registry.py --check` — validate and exit
- `python scripts/validate_service_registry.py --list` — list all registered services

### Step 4: Migrate directus_runtime as reference

1. Add the derivation include at the top of `directus_runtime/tasks/main.yml`:
   ```yaml
   - name: Derive Directus conventional defaults from the service registry
     ansible.builtin.include_role:
       name: lv3.platform.common
       tasks_from: derive_service_defaults
     vars:
       common_derive_service_name: directus
   ```

2. Remove all conventional variables from `directus_runtime/defaults/main.yml`. Keep only service-specific defaults (admin_email, health_path, ping_path, etc.).

3. Trim `directus_runtime/meta/argument_specs.yml` — remove specs for derived variables.

4. Verify: `ansible-playbook playbooks/directus.yml -e env=production --check -vvv`
   Check that all variables resolve to the same values as before.

### Step 5: Migrate remaining roles in batches

For each role:
1. Add the derivation include at the top of tasks/main.yml
2. Remove conventional variables from defaults/main.yml (keep service-specific ones)
3. Trim argument_specs.yml
4. Verify with --check

Work in batches of 5-8 roles. After each batch: `make validate-ansible-syntax`

**Rollback safety:** If a migration breaks, temporarily re-add the removed defaults. `set_fact` (from the derivation) has higher precedence than defaults, so having both is safe.

### Step 6: Gate integration

Add `python scripts/validate_service_registry.py --check` to the validation gate. Check how other catalog validators are called (look in `Makefile` for `validate-schemas` or `.githooks/pre-push`).

## Rules you must follow

- Do NOT remove defaults/main.yml files entirely — they still hold service-specific defaults.
- Do NOT use a custom Ansible vars plugin. Use set_fact via include_role.
- Do NOT rename existing variables. Derived variables use the exact same names as today's defaults.
- Do NOT add speculative fields to the registry.
- Do NOT generate Jinja2 templates from the registry.
- Read `AGENTS.md` and `CLAUDE.md` at the repo root before starting.
- This is a branch-local change. Do NOT modify VERSION, changelog.md, RELEASE.md, or README.md.
```

---

## Prompt 7: ADR 0374 — Cross-Cutting Service Manifest

```
You are implementing ADR 0374 from this repository. Read `docs/adr/0374-cross-cutting-service-manifest.md` completely before writing any code. Follow it exactly.

## Prerequisites

ADRs 0368, 0369, and 0373 must be implemented first. This ADR extends the service registry (0373) with cross-cutting declarations and uses the validation toolkit (0369) and compose macros (0368).

## Your task — PHASE 1 ONLY (Hairpin concern)

The ADR specifies 5 phases. Implement ONLY Phase 1 (hairpin) in this session. The other phases require more design iteration.

### Step 1: Add hairpin declarations to the service registry

Edit `inventory/group_vars/platform_services.yml`. For each service that currently has `extra_hosts` in its compose template, add a `hairpin.publish` section:

Find all services with extra_hosts:
```
grep -rl "extra_hosts" collections/ansible_collections/lv3/platform/roles/*/templates/docker-compose.yml.j2
```

For each, read the compose template and extract the hostname:address pairs. Add them to the registry:
```yaml
  outline:
    # ... existing fields ...
    hairpin:
      publish:
        - hostname: agents.example.com
          address_host: nginx-edge
```

Note: `address_host` is an inventory hostname, NOT a raw IP. The generator resolves it.

### Step 2: Create the generator script

Create `scripts/generate_cross_cutting_artifacts.py` with:

1. `--check` mode: Validates hairpin declarations (all address_host values must exist in platform_guest_catalog)
2. `--write --only hairpin` mode: Generates `inventory/group_vars/platform_hairpin.yml` containing `platform_hairpin_nat_hosts`

The generated file format:
```yaml
# GENERATED — do not edit. Source: platform_service_registry hairpin declarations.
# Regenerate: python scripts/generate_cross_cutting_artifacts.py --write --only hairpin
platform_hairpin_nat_hosts:
  - hostname: agents.example.com
    address: 10.10.10.92
  - hostname: data.example.com
    address: 10.10.10.92
  # ... deduplicated and sorted
```

The script must:
- Load `inventory/group_vars/platform_services.yml` for the registry
- Load `inventory/group_vars/platform.yml` (or wherever `platform_guest_catalog` lives) for IP resolution
- Use `from validation_toolkit import ...` for input validation
- NOT import `requests` at module load time
- Support `--check` and `--write` with `--only hairpin` filter

### Step 3: Generate and verify

```bash
# Generate the hairpin variable:
python scripts/generate_cross_cutting_artifacts.py --write --only hairpin

# Compare with the manually maintained list from ADR 0368:
# The generated list should match or be a superset of platform_hairpin_nat_hosts
diff inventory/group_vars/platform_hairpin.yml <previous manual version>
```

### Step 4: Replace manual extra_hosts in compose templates

For each compose template that has manual `extra_hosts`, verify that:
1. All its hostname entries are now in the generated `platform_hairpin_nat_hosts`
2. The `hairpin_hosts()` macro from ADR 0368 is being used (or add it if ADR 0368 migration hasn't reached this role yet)

### Step 5: Add to gate validation

Add `python scripts/generate_cross_cutting_artifacts.py --check` to the validation gate alongside other catalog validators.

## Rules you must follow

- The generator must NOT make live API calls (no Hetzner, no Keycloak, no cert issuance).
- The generator must NOT modify files outside config/generated/, inventory/group_vars/platform_hairpin.yml.
- The generator must NOT import requests at module load time.
- Do NOT add cross-cutting fields to the registry that have no generator consuming them yet.
- Read `AGENTS.md` and `CLAUDE.md` at the repo root before starting.
- This is a branch-local change. Do NOT modify VERSION, changelog.md, RELEASE.md, or README.md.
```

---

## Prompt 8: ADR 0374 Phase 2 — DNS Publication

```
You are implementing Phase 2 (DNS publication) of ADR 0374. Read `docs/adr/0374-cross-cutting-service-manifest.md` completely, focusing on the "Phase 2: DNS Publication" section before writing code.

## Your task

Phase 2 extends `scripts/generate_cross_cutting_artifacts.py` to generate DNS declarations for services that need external hostnames (not hairpin internal).

### Prerequisites
- ADR 0369 (validation toolkit) is implemented
- ADR 0373 (service registry) exists with service entries
- Phase 1 (hairpin) is working — the generator structure exists

### Step 1: Extend the service registry schema

In `inventory/group_vars/platform_services.yml`, add optional `dns` section to each service entry that needs external DNS:

```yaml
platform_service_registry:
  directus:
    image_catalog_key: directus_runtime
    internal_port: 8055
    host_group: docker_runtime_lv3
    dns:
      fqdn: directus.example.com
      type: public  # or 'internal' for split-view
      ttl: 3600
```

### Step 2: Implement DNS generator in the script

Add to `scripts/generate_cross_cutting_artifacts.py`:

```python
def generate_dns_declarations(registry, catalog, write=False):
    """
    Generate DNS declarations for services with dns section.
    Output: config/generated/dns-declarations.yaml
    """
    declarations = {}

    for service_name, service_config in registry.items():
        dns_config = service_config.get('dns')
        if not dns_config:
            continue

        fqdn = require_str(dns_config.get('fqdn'), f'platform_service_registry.{service_name}.dns.fqdn')
        dns_type = require_enum(dns_config.get('type'), ['public', 'internal'], f'platform_service_registry.{service_name}.dns.type')
        ttl = require_int(dns_config.get('ttl'), f'platform_service_registry.{service_name}.dns.ttl')

        declarations[fqdn] = {
            'service': service_name,
            'type': dns_type,
            'ttl': ttl
        }

    if write:
        with open('config/generated/dns-declarations.yaml', 'w') as f:
            yaml.dump({'dns_records': declarations}, f, default_flow_style=False)

    return declarations
```

### Step 3: Integrate with cross-cutting workflow

Update the main function in `generate_cross_cutting_artifacts.py` to call:
```python
if phase == 'dns' or phase == 'all':
    dns_decls = generate_dns_declarations(registry, catalog, write=write)
    if not write:
        print(f"DNS: {len(dns_decls)} declarations would be generated")
```

### Step 4: Add validation

Create `scripts/validate_dns_declarations.py` that:
- Loads `config/generated/dns-declarations.yaml`
- Checks each FQDN is well-formed (matches pattern `[a-z0-9]([a-z0-9-]*\.)+lv3\.org`)
- Warns if two services declare the same FQDN
- Fails if any FQDN lacks matching platform_service_registry entry

### Step 5: Test

```bash
python scripts/generate_cross_cutting_artifacts.py --check --only dns
python scripts/validate_dns_declarations.py --check
```

## Rules you must follow

- DNS generator must NOT make actual DNS API calls
- Must validate FQDN format matches domain policy
- Must NOT overwrite manually maintained DNS records
- One service = one FQDN (no CNAME synthesis yet)
- Do NOT add DNS fields to registry entries that are internal-only
```

---

## Prompt 9: ADR 0374 Phase 3 — TLS Certificate Management

```
You are implementing Phase 3 (TLS certificate management) of ADR 0374. Read `docs/adr/0374-cross-cutting-service-manifest.md` completely, focusing on the "Phase 3: TLS Certificate Management" section.

## Your task

Phase 3 generates TLS certificate declarations and verifies they exist or have a provisioning plan.

### Prerequisites
- Phase 2 (DNS) is working
- ADR 0370 (service lifecycle tasks) exists
- Roles can read from `inventory/group_vars/platform_tls_certs.yml`

### Step 1: Extend registry with TLS section

In `inventory/group_vars/platform_services.yml`, add optional `tls` section:

```yaml
platform_service_registry:
  directus:
    # ... existing fields ...
    tls:
      cert_source: letsencrypt  # or 'openbao', 'self-signed'
      wildcard: false
      cert_validity_days: 90
```

### Step 2: Implement TLS generator

Add to `scripts/generate_cross_cutting_artifacts.py`:

```python
def generate_tls_certificates(registry, catalog, write=False):
    """
    Generate TLS certificate declarations.
    Output: inventory/group_vars/platform_tls_certs.yml
    """
    certs = {}

    for service_name, service_config in registry.items():
        tls_config = service_config.get('tls')
        if not tls_config:
            continue

        dns_config = service_config.get('dns')
        if not dns_config:
            raise ValueError(f'{service_name}: TLS requires dns section')

        fqdn = dns_config['fqdn']
        cert_source = require_enum(tls_config.get('cert_source'), ['letsencrypt', 'openbao', 'self-signed'], f'platform_service_registry.{service_name}.tls.cert_source')
        wildcard = require_bool(tls_config.get('wildcard', False), f'platform_service_registry.{service_name}.tls.wildcard')

        certs[fqdn] = {
            'service': service_name,
            'source': cert_source,
            'wildcard': wildcard,
            'provisioned': False  # Mark as needing provisioning
        }

    if write:
        with open('inventory/group_vars/platform_tls_certs.yml', 'w') as f:
            yaml.dump({'platform_tls_certs': certs}, f, default_flow_style=False)

    return certs
```

### Step 3: Add provisioning task

Create `roles/common/tasks/provision_tls_certs.yml`:
- Called by service playbooks before container startup
- Checks if cert exists in `/etc/lv3/certs/{fqdn}/`
- If not, provisioning method depends on `cert_source`:
  - `letsencrypt`: call Ansible certbot module
  - `openbao`: call openbao_agent to fetch from PKI
  - `self-signed`: generate with openssl

### Step 4: Validate

Create `scripts/validate_tls_certs.py` that:
- Checks all TLS entries have matching DNS entry
- Warns if cert_source=letsencrypt but domain is .internal
- Lists which certs need provisioning

### Step 5: Integration

Update service playbooks to include the provisioning task before `docker_compose_converge.yml`

## Rules you must follow

- Do NOT provision actual certificates in --check mode
- Must track which certs are self-signed vs. production
- Must warn if same domain used by multiple services (conflict)
- Do NOT expose private keys in generated artifacts
```

---

## Prompt 10: ADR 0374 Phase 4 — Nginx Edge Publication

```
You are implementing Phase 4 (Nginx edge publication / reverse proxy) of ADR 0374. Read `docs/adr/0374-cross-cutting-service-manifest.md` completely, focusing on the "Phase 4: Nginx Edge Publication" section.

## Your task

Phase 4 generates nginx upstream declarations and edge publication rules from the service registry.

### Prerequisites
- Phase 3 (TLS) is working
- ADR 0365 (playbook composition) exists with nginx playbook includes
- Nginx role can read from `config/generated/nginx-upstreams.conf`

### Step 1: Extend registry with proxy section

In `inventory/group_vars/platform_services.yml`, add optional `proxy` section:

```yaml
platform_service_registry:
  directus:
    # ... existing fields ...
    proxy:
      enabled: true
      upstream_port: 8055  # service's internal port
      path_prefix: /
      auth_required: true  # or false for public services
      rate_limit: "10r/s"
```

### Step 2: Implement nginx generator

Add to `scripts/generate_cross_cutting_artifacts.py`:

```python
def generate_nginx_upstreams(registry, catalog, write=False):
    """
    Generate nginx upstream definitions and location blocks.
    Output: config/generated/nginx-upstreams.conf
    """
    upstreams = []

    for service_name, service_config in registry.items():
        proxy_config = service_config.get('proxy')
        if not proxy_config or not proxy_config.get('enabled'):
            continue

        dns_config = service_config.get('dns')
        if not dns_config:
            raise ValueError(f'{service_name}: proxy requires dns section')

        fqdn = dns_config['fqdn']
        upstream_port = require_int(proxy_config.get('upstream_port'), f'platform_service_registry.{service_name}.proxy.upstream_port')
        auth_required = require_bool(proxy_config.get('auth_required', False), f'platform_service_registry.{service_name}.proxy.auth_required')
        path_prefix = require_str(proxy_config.get('path_prefix', '/'), f'platform_service_registry.{service_name}.proxy.path_prefix')

        upstream_name = f'{service_name}_upstream'
        upstreams.append({
            'name': upstream_name,
            'service_name': service_name,
            'fqdn': fqdn,
            'port': upstream_port,
            'path': path_prefix,
            'auth_required': auth_required
        })

    if write:
        # Generate nginx config
        nginx_conf = _render_nginx_upstreams(upstreams)
        with open('config/generated/nginx-upstreams.conf', 'w') as f:
            f.write(nginx_conf)

    return upstreams

def _render_nginx_upstreams(upstreams):
    """Render nginx upstream blocks as text"""
    lines = ['# Generated by ADR 0374 Phase 4 — do not edit manually\n']

    for upstream in upstreams:
        lines.append(f"upstream {upstream['name']} {{")
        lines.append(f"  server 10.10.10.92:{upstream['port']};  # {upstream['service_name']}")
        lines.append("}\n")

    return ''.join(lines)
```

### Step 3: Generate location blocks

Add template for edge nginx role that includes upstreams:
```nginx
server {
    listen 443 ssl http2;
    server_name _;

    ssl_certificate /etc/lv3/certs/edge.example.com/fullchain.pem;
    ssl_certificate_key /etc/lv3/certs/edge.example.com/privkey.pem;

    include config/generated/nginx-upstreams.conf;

    # Location blocks for each upstream
    {% for upstream in platform_nginx_upstreams %}
    location {{ upstream.path_prefix }} {
        proxy_pass http://{{ upstream.name }};
        proxy_set_header Host $host;
        {% if upstream.auth_required %}
        auth_request /oauth2/auth;
        {% endif %}
    }
    {% endfor %}
}
```

### Step 4: Validate

Create `scripts/validate_nginx_config.py` that:
- Parses generated nginx config
- Checks upstream ports match service internal_port
- Warns if service has proxy enabled but no dns entry
- Tests that nginx can syntax-check the config (via `nginx -t`)

### Step 5: Integration

Update `playbooks/_includes/nginx_edge_publication.yml` to:
1. Call generator: `generate_cross_cutting_artifacts.py --write --only proxy`
2. Include generated upstream file
3. Reload nginx after changes

## Rules you must follow

- Do NOT modify /etc/nginx/sites-enabled directly — always generate
- Must NOT proxy to 0.0.0.0 or 127.0.0.1 (use 10.10.10.92 for runtime)
- Generated config must pass `nginx -t` validation
- One service = one upstream block (no multiplexing yet)
```

---

## Prompt 11: ADR 0374 Phase 5 — SSO Client Provisioning

```
You are implementing Phase 5 (SSO client provisioning) of ADR 0374. Read `docs/adr/0374-cross-cutting-service-manifest.md` completely, focusing on the "Phase 5: SSO Client Provisioning" section.

## Your task

Phase 5 generates Keycloak SSO client declarations and integrates with the OpenBao secret pipeline to provision and distribute client credentials.

### Prerequisites
- All prior phases (1-4) are working
- ADR 0373 (service registry with derived defaults) exists
- OpenBao is running with Keycloak OIDC PKI role
- Keycloak admin API is accessible

### Step 1: Extend registry with SSO section

In `inventory/group_vars/platform_services.yml`, add optional `sso` section:

```yaml
platform_service_registry:
  directus:
    # ... existing fields ...
    sso:
      enabled: true
      provider: keycloak
      client_name: directus_runtime
      redirect_uris:
        - https://directus.example.com/auth/callback
      scopes: [openid, profile, email]
      public_client: false
```

### Step 2: Implement SSO client generator

Add to `scripts/generate_cross_cutting_artifacts.py`:

```python
def generate_sso_clients(registry, catalog, write=False):
    """
    Generate SSO client declarations.
    Output: config/generated/sso-clients.yaml
    """
    clients = {}

    for service_name, service_config in registry.items():
        sso_config = service_config.get('sso')
        if not sso_config or not sso_config.get('enabled'):
            continue

        client_name = require_str(sso_config.get('client_name'), f'platform_service_registry.{service_name}.sso.client_name')
        provider = require_enum(sso_config.get('provider'), ['keycloak', 'oauth2-proxy'], f'platform_service_registry.{service_name}.sso.provider')
        redirect_uris = require_string_list(sso_config.get('redirect_uris', []), f'platform_service_registry.{service_name}.sso.redirect_uris')
        scopes = require_string_list(sso_config.get('scopes', ['openid', 'profile']), f'platform_service_registry.{service_name}.sso.scopes')
        public_client = require_bool(sso_config.get('public_client', False), f'platform_service_registry.{service_name}.sso.public_client')

        clients[client_name] = {
            'service': service_name,
            'provider': provider,
            'redirect_uris': redirect_uris,
            'scopes': scopes,
            'public_client': public_client,
            'provisioned': False
        }

    if write:
        with open('config/generated/sso-clients.yaml', 'w') as f:
            yaml.dump({'sso_clients': clients}, f, default_flow_style=False)

    return clients
```

### Step 3: Create SSO provisioning task

Create `roles/common/tasks/provision_sso_clients.yml`:
- Called by service playbooks during converge
- For each client in `sso_clients`:
  1. Check if client exists in Keycloak (via API)
  2. If not, create it with provided redirect_uris and scopes
  3. Generate client secret and store in OpenBao at `secret/data/sso/{client_name}`
  4. Create env file `<service_dir>/.env.sso` with OIDC_CLIENT_ID and OIDC_CLIENT_SECRET
- Must be idempotent — second run skips existing clients

### Step 4: Integrate with service playbooks

Update service playbooks that have `sso.enabled: true` to:
1. Include `roles/common/tasks/provision_sso_clients.yml` before docker_compose_converge
2. Reference the generated `sso_clients` list

Example in playbook:
```yaml
- name: Provision SSO clients
  include_tasks: roles/common/tasks/provision_sso_clients.yml
  vars:
    sso_clients_to_provision: "{{ sso_clients | selectattr('service', 'equalto', inventory_hostname) | list }}"
```

### Step 5: Add secret injection to compose environment

Extend `roles/common/tasks/manage_service_secrets.yml` to:
- Read generated SSO secrets from OpenBao
- Inject `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` into compose env files for services with sso.enabled=true

### Step 6: Validation

Create `scripts/validate_sso_clients.py` that:
- Loads `config/generated/sso-clients.yaml`
- For each client:
  - Checks redirect_uris are HTTPS and match service dns.fqdn
  - Validates scopes are in Keycloak allowed list
  - Warns if public_client=true (less secure)
  - Checks OpenBao path exists with credentials

### Step 7: Test

```bash
python scripts/generate_cross_cutting_artifacts.py --check --only sso
python scripts/validate_sso_clients.py --check
make converge-<service> env=development  # Verify SSO env vars injected
```

## Rules you must follow

- Do NOT make real Keycloak API calls in --check mode
- Client secrets must NEVER appear in generated files (only in OpenBao)
- Must validate redirect_uris match service FQDN before provisioning
- One service = one SSO client (no sharing)
- Do NOT provision SSO if service has no dns.fqdn
- Do NOT auto-delete Keycloak clients on service removal (manual cleanup)
- Read `AGENTS.md` and `CLAUDE.md` at the repo root before starting
```
