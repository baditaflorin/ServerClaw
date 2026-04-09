# ADR 0372: Data-Driven Playbook Composition

- **Date**: 2026-04-06
- **Status**: Accepted
- **Deciders**: platform team
- **Concern**: platform, dry
- **Tags**: ansible, playbooks, dry, composition, dns

## Context

The platform maintains ~50 top-level playbooks under `collections/ansible_collections/lv3/platform/playbooks/`. These playbooks are structurally identical — they compose 3-5 "plays" from a fixed set of building blocks:

| Building block (play) | Duplicated in | Lines per occurrence |
|---|---|---|
| Hetzner DNS publication | 16 playbooks | 58-60 lines |
| PostgreSQL preparation | 10+ playbooks | 20-25 lines |
| Docker runtime convergence | 31 playbooks | 15-20 lines |
| NGINX edge publication | 16 playbooks | 15-20 lines |
| Post-verify + notify | 11-24 playbooks | 8-10 lines |

Additionally, **host selector patterns** are copy-pasted with the staging/production conditional:
```yaml
hosts: "{{ 'docker-runtime-staging-lv3' if (env | default('production')) == 'staging' else 'docker-runtime-lv3' }}"
```
This exact line appears in 30+ playbooks.

### The Hetzner DNS block — worst offender

The DNS publication play is **58-60 lines** of identical code in 16 playbooks, differing only in the `subdomain_fqdn` value. The full block:

1. Loads `inventory/group_vars/all.yml` (to get `hetzner_dns_zone_name`)
2. Loads `config/subdomain-catalog.json`
3. Selects the matching subdomain entry
4. Asserts it exists and is active
5. Derives the Hetzner record name
6. Calls the `hetzner_dns_record` role

This is **928 lines** (58 × 16) of near-identical YAML that differ only in the FQDN.

### The directus.yml example

The `directus.yml` playbook (176 lines) contains 6 plays:
1. DNS publication (lines 27-85) — **58 lines, identical to 15 other playbooks**
2. PostgreSQL prep (lines 87-104) — **17 lines, identical to 9 other playbooks**
3. Docker runtime converge (lines 106-125) — **19 lines, identical to 30 other playbooks**
4. Access model seed (lines 127-145) — **Service-specific**
5. NGINX edge publication (lines 147-164) — **17 lines, identical to 15 other playbooks**
6. Public verification (lines 166-176) — **10 lines, semi-unique**

Only plays 4 and 6 are Directus-specific. The other 4 plays (112 lines) are pure boilerplate.

## Decision

Extract the four repeated play patterns into **shared playbook includes** and create a **service descriptor** format that drives playbook composition.

### Approach: shared play includes + per-service vars files

Instead of generating playbooks (which would break `ansible-playbook` tab-completion and git blame), extract the repeated plays into includable playbook files and have each service playbook `import_playbook` them.

**Note:** Ansible does not support `import_playbook` with `vars`. Instead, we use the following pattern: each repeated play becomes a standalone playbook that reads its parameters from a well-known variable.

### File structure

```
playbooks/
  _includes/
    dns_publication.yml          # The 58-line DNS block, parameterized
    postgres_preparation.yml     # The 25-line postgres block, parameterized
    docker_runtime_converge.yml  # The 20-line converge block, parameterized
    nginx_edge_publication.yml   # The 20-line nginx block, parameterized
  vars/
    directus.yml                 # Service-specific variables for directus
    flagsmith.yml                # Service-specific variables for flagsmith
    ...
  directus.yml                   # Thin orchestrator that imports includes
  flagsmith.yml                  # Same pattern
  ...
```

### Include file 1: `_includes/dns_publication.yml`

This file replaces the 58-line DNS block duplicated across 16 playbooks. It expects one variable: `service_dns_fqdn`.

**Exact implementation:**

```yaml
---
# _includes/dns_publication.yml
# Purpose: Converge a single Hetzner DNS A record from the subdomain catalog.
# Input: service_dns_fqdn (string) — the FQDN to publish (e.g., "data.lv3.org")
# Usage: import_playbook with -e service_dns_fqdn=data.lv3.org, or set in a vars file.

- name: "Ensure Hetzner DNS publication for {{ service_dns_fqdn }}"
  hosts: localhost
  connection: local
  gather_facts: false
  vars:
    subdomain_catalog_path: "{{ playbook_dir }}/../../../../../config/subdomain-catalog.json"
    inventory_defaults_path: "{{ playbook_dir }}/../../../../../inventory/group_vars/all.yml"

  tasks:
    - name: Load controller defaults
      ansible.builtin.include_vars:
        file: "{{ inventory_defaults_path }}"

    - name: Load the subdomain catalog
      ansible.builtin.include_vars:
        file: "{{ subdomain_catalog_path }}"
        name: subdomain_catalog

    - name: "Select the {{ service_dns_fqdn }} subdomain entry"
      ansible.builtin.set_fact:
        selected_subdomain: >-
          {{
            (
              subdomain_catalog.subdomains
              | selectattr('fqdn', 'equalto', service_dns_fqdn)
              | list
              | first
            ) | default({})
          }}

    - name: "Assert {{ service_dns_fqdn }} is catalogued"
      ansible.builtin.assert:
        that:
          - selected_subdomain != {}
          - selected_subdomain.status in ['active', 'planned']
          - selected_subdomain.fqdn.endswith(hetzner_dns_zone_name)
        fail_msg: "{{ service_dns_fqdn }} must exist in config/subdomain-catalog.json before live apply."

    - name: Derive the managed Hetzner record name
      ansible.builtin.set_fact:
        selected_subdomain_record_name: >-
          {{
            '@'
            if selected_subdomain.fqdn == hetzner_dns_zone_name
            else (
              selected_subdomain.fqdn.rsplit('.' ~ hetzner_dns_zone_name, 1)[0]
            )
          }}

    - name: "Converge the {{ service_dns_fqdn }} Hetzner DNS record"
      ansible.builtin.include_role:
        name: lv3.platform.hetzner_dns_record
      vars:
        hetzner_dns_record_zone_name: "{{ hetzner_dns_zone_name }}"
        hetzner_dns_record_name: "{{ selected_subdomain_record_name }}"
        hetzner_dns_record_type: A
        hetzner_dns_record_value: "{{ selected_subdomain.target }}"
        hetzner_dns_record_ttl: "{{ selected_subdomain.ttl | default(60) }}"
```

### Include file 2: `_includes/postgres_preparation.yml`

**Input variables:**
- `service_postgres_role` (string): The postgres role name (e.g., `lv3.platform.directus_postgres`)

```yaml
---
- name: "Prepare PostgreSQL for {{ service_postgres_role | regex_replace('lv3\\.platform\\.', '') }}"
  hosts: "{{ 'postgres-staging-lv3' if (env | default('production')) == 'staging' else 'postgres-lv3' }}"
  become: true
  gather_facts: true

  pre_tasks:
    - name: Run shared preflight checks
      ansible.builtin.import_tasks: tasks/preflight.yml
      vars:
        playbook_execution_require_debian: true
        playbook_execution_emit_audit: false
        required_hosts:
          - "{{ playbook_execution_required_hosts.postgres[playbook_execution_env] }}"

  roles:
    - role: lv3.platform.linux_guest_firewall
    - role: lv3.platform.postgres_vm
    - role: "{{ service_postgres_role }}"
```

### Include file 3: `_includes/docker_runtime_converge.yml`

**Input variables:**
- `service_runtime_roles` (list): Ordered list of roles to apply (e.g., `[lv3.platform.docker_runtime, lv3.platform.keycloak_runtime, lv3.platform.directus_runtime]`)
- `service_audit_name` (string): Service name for audit logging (e.g., `directus`)

```yaml
---
- name: "Converge {{ service_audit_name }} on the Docker runtime VM"
  hosts: "{{ 'docker-runtime-staging-lv3' if (env | default('production')) == 'staging' else 'docker-runtime-lv3' }}"
  become: true
  gather_facts: true

  pre_tasks:
    - name: Run shared preflight checks
      ansible.builtin.import_tasks: tasks/preflight.yml
      vars:
        playbook_execution_require_debian: true
        playbook_execution_audit_action: "playbook.start.{{ service_audit_name }}"
        playbook_execution_audit_target: "{{ service_audit_name }}"
        required_hosts:
          - "{{ playbook_execution_required_hosts.docker_runtime[playbook_execution_env] }}"

  tasks:
    - name: Apply prerequisite and runtime roles
      ansible.builtin.include_role:
        name: "{{ role_item }}"
      loop: "{{ [('lv3.platform.linux_guest_firewall')] + service_runtime_roles }}"
      loop_control:
        loop_var: role_item
```

**Note:** The `roles:` directive does not support dynamic role lists. Instead, we use `include_role` in a loop within `tasks:`. The roles execute in the order specified in `service_runtime_roles`.

### Include file 4: `_includes/nginx_edge_publication.yml`

**Input variables:**
- `service_audit_name` (string): Service name for logging.

```yaml
---
- name: "Publish {{ service_audit_name }} through the NGINX edge"
  hosts: "{{ 'nginx-staging-lv3' if (env | default('production')) == 'staging' else 'nginx-lv3' }}"
  become: true
  gather_facts: true
  vars_files:
    - "{{ playbook_dir }}/../../../../../inventory/group_vars/platform.yml"

  pre_tasks:
    - name: Run shared preflight checks
      ansible.builtin.import_tasks: tasks/preflight.yml
      vars:
        playbook_execution_require_debian: true
        playbook_execution_emit_audit: false
        required_hosts:
          - "{{ playbook_execution_required_hosts.nginx_edge[playbook_execution_env] }}"

  roles:
    - role: lv3.platform.nginx_edge_publication
```

### Per-service vars file format

Each service declares its composition needs in `playbooks/vars/<service>.yml`:

```yaml
---
# playbooks/vars/directus.yml
service_audit_name: directus
service_dns_fqdn: data.lv3.org
service_postgres_role: lv3.platform.directus_postgres
service_runtime_roles:
  - lv3.platform.docker_runtime
  - lv3.platform.keycloak_runtime
  - lv3.platform.directus_runtime
service_needs_dns: true
service_needs_postgres: true
service_needs_nginx_edge: true
```

### Migrated playbook example: `directus.yml`

After migration, the directus playbook becomes a thin orchestrator:

```yaml
---
# Playbook: directus.yml
# Purpose: Converge the Directus PostgreSQL backend, runtime, Keycloak client, and shared-edge publication.

# --- Standard plays (driven by vars/directus.yml) ---

- name: Load service descriptor
  hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - name: Load Directus service vars
      ansible.builtin.include_vars:
        file: "{{ playbook_dir }}/vars/directus.yml"

- import_playbook: _includes/dns_publication.yml
  when: service_needs_dns | default(false)

- import_playbook: _includes/postgres_preparation.yml
  when: service_needs_postgres | default(false)

- import_playbook: _includes/docker_runtime_converge.yml

# --- Directus-specific plays ---

- name: Seed the Directus access model in PostgreSQL
  hosts: "{{ 'postgres-staging-lv3' if (env | default('production')) == 'staging' else 'postgres-lv3' }}"
  become: true
  gather_facts: true
  pre_tasks:
    - name: Run shared preflight checks
      ansible.builtin.import_tasks: tasks/preflight.yml
      vars:
        playbook_execution_require_debian: true
        playbook_execution_emit_audit: false
        required_hosts:
          - "{{ playbook_execution_required_hosts.postgres[playbook_execution_env] }}"
  tasks:
    - name: Seed the Directus roles, policies, permissions, and service token user
      ansible.builtin.include_role:
        name: lv3.platform.directus_postgres
        tasks_from: access_model.yml

- import_playbook: _includes/nginx_edge_publication.yml
  when: service_needs_nginx_edge | default(false)

- name: Verify the public Directus publication
  hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - name: Verify the Directus public data API and SSO redirect path
      ansible.builtin.include_role:
        name: lv3.platform.directus_runtime
        tasks_from: publish.yml
```

### Important Ansible limitation: `import_playbook` with `when`

`import_playbook` supports `when` conditionals as of Ansible 2.15+. The platform should already be on this version. If not, the `when:` clauses can be moved inside the include files as `when:` on each play.

Additionally, `import_playbook` does **not** support `vars:` — the variables must be loaded beforehand via `include_vars` in a preceding play, or passed as `-e` extra vars.

**Critical:** The `import_playbook` `when` condition is evaluated in the context of the play that loaded the vars. This means the `include_vars` play must run **before** any `import_playbook` that references those vars.

### Variable propagation

Variables loaded in one play are **not** automatically available in subsequent plays (Ansible scoping). To make `service_dns_fqdn` et al. available to the included playbooks:

**Option A (recommended):** Pass the vars file path via `-e`:
```bash
ansible-playbook playbooks/directus.yml -e @playbooks/vars/directus.yml -e env=production
```

**Option B:** Use `set_fact` with `cacheable: true` in the first play.

**Option C:** Use a `group_vars` file that is included by all plays.

**Decision:** Use Option A. The service playbook's top-level comment documents the required `-e` invocation. The `Makefile` target handles this automatically:

```makefile
converge-directus:
	$(ANSIBLE_PLAYBOOK_CMD) playbooks/directus.yml \
		-e @playbooks/vars/directus.yml \
		-e env=$(env)
```

### Migration procedure

#### Phase 1: Create the `_includes/` directory and all four include files

```bash
mkdir -p collections/ansible_collections/lv3/platform/playbooks/_includes
# Write all four files
git add playbooks/_includes/
git commit -m "feat(playbooks): add shared playbook includes for DNS, postgres, docker, nginx — ADR 0372"
```

#### Phase 2: Create the `vars/` directory and service descriptor for `directus`

```bash
mkdir -p collections/ansible_collections/lv3/platform/playbooks/vars
# Write vars/directus.yml
git add playbooks/vars/
```

#### Phase 3: Migrate `directus.yml` and verify

```bash
# Before:
ansible-playbook playbooks/directus.yml -e env=production --check --diff 2>&1 | tee /tmp/before.log

# After migration:
ansible-playbook playbooks/directus.yml -e @playbooks/vars/directus.yml -e env=production --check --diff 2>&1 | tee /tmp/after.log

# Compare task names and actions (ignoring timing):
diff <(grep '^TASK' /tmp/before.log) <(grep '^TASK' /tmp/after.log)
```

#### Phase 4: Migrate remaining playbooks in batches

Prioritize by the number of standard plays (DNS + postgres + docker + nginx):

1. **Full standard stack** (all 4 plays): flagsmith, glitchtip, label-studio, lago, n8n, nextcloud, superset, plausible — 8 playbooks
2. **Docker + nginx** (2 plays): headscale, ntfy, dozzle, livekit — 4 playbooks
3. **Docker only** (1 play): ollama, open-webui, searxng — 3 playbooks
4. **Remaining**: custom compositions

#### Phase 5: Update Makefile targets

After migrating each playbook, update its `make converge-<service>` target to pass `-e @playbooks/vars/<service>.yml`.

### What NOT to do

- Do **not** delete the per-service playbook files. They remain as orchestration entry points. The goal is to shrink them, not eliminate them.
- Do **not** create a single "meta-playbook" that deploys all services. Each service must be independently deployable.
- Do **not** use `ansible.builtin.include_playbook` (it doesn't exist) — use `import_playbook` at the top level.
- Do **not** put service-specific plays (like the Directus access model seed) into the shared includes. Those stay in the service playbook.
- Do **not** change the `playbook_dir`-relative paths in the includes. The `_includes/` files are in the same directory as the service playbooks, so relative paths remain the same.

## Consequences

**Positive:**
- Eliminates ~928 lines of duplicated DNS publication YAML across 16 playbooks.
- Eliminates ~250 lines of duplicated PostgreSQL preparation across 10 playbooks.
- Eliminates ~620 lines of duplicated Docker convergence preflight across 31 playbooks.
- Eliminates ~320 lines of duplicated NGINX publication across 16 playbooks.
- Total: **~2,100 lines** of duplicated playbook YAML removed.
- Adding a new service playbook becomes: write a `vars/<service>.yml` descriptor + a thin playbook with `import_playbook` calls.
- Fixing a cross-cutting issue (e.g., changing the staging host selector) requires editing 4 include files instead of 50 playbooks.

**Negative / Trade-offs:**
- `import_playbook` is a top-level directive — it cannot be wrapped in blocks or conditionals in older Ansible versions. Requires Ansible 2.15+.
- Variable scoping requires careful handling via `-e @vars/file.yml` or `set_fact cacheable`.
- `ansible-playbook --list-tasks` will show the include structure, which may be confusing initially. Clear play names mitigate this.

## Implementation plan

1. Create `playbooks/_includes/dns_publication.yml`
2. Create `playbooks/_includes/postgres_preparation.yml`
3. Create `playbooks/_includes/docker_runtime_converge.yml`
4. Create `playbooks/_includes/nginx_edge_publication.yml`
5. Create `playbooks/vars/directus.yml` and migrate `directus.yml`
6. Verify behaviour is identical
7. Migrate remaining 15 DNS-using playbooks
8. Migrate remaining postgres/docker/nginx playbooks
9. Update all Makefile `converge-*` targets

## Depends on

- ADR 0021 (Docker Runtime) — the convergence pattern being extracted
- ADR 0042 (Hetzner DNS) — the DNS publication pattern being extracted

## Related

- ADR 0370 (Service Lifecycle Task Includes) — handles role-level task duplication; this ADR handles playbook-level duplication
- ADR 0373 (Service Registry) — the vars files this ADR introduces are precursors to the full service registry
