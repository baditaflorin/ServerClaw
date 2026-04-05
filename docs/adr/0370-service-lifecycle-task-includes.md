# ADR 0363: Service Lifecycle Task Includes

- **Date**: 2026-04-06
- **Status**: Proposed
- **Deciders**: platform team
- **Concern**: platform, dry
- **Tags**: ansible, roles, dry, lifecycle, tasks

## Context

~40 runtime roles under `collections/ansible_collections/lv3/platform/roles/*_runtime/tasks/main.yml` repeat the same multi-step service lifecycle sequence. The `directus_runtime` role (411 lines) is a representative example. Its `tasks/main.yml` contains these phases:

| Phase | Lines | Description | Duplicated across |
|---|---|---|---|
| 1. Input validation | 8-28 | `assert` on required variables | 8+ roles |
| 2. Check secrets on control machine | 30-70 | `stat` + `fail` per secret file | 4+ roles |
| 3. Create directories | 81-92 | `file` with `loop` | 5+ roles (partially extracted) |
| 4. Generate secrets | 94-113 | `shell` with idempotent openssl | 3+ roles |
| 5. Read + record secrets | 115-138 | `slurp` + `set_fact` + `b64decode` | 4+ roles |
| 6. Mirror secrets to localhost | 140-162 | `copy` with `delegate_to: localhost` | 3+ roles |
| 7. OpenBao agent setup | 164-197 | `include_role: common/openbao_compose_env` | **Already extracted** (35 roles) |
| 8. Render templates | 199-216 | `template` for env + compose | All roles |
| 9. Pull image | 218-235 | `docker compose pull` | All roles |
| 10. Docker NAT chain recovery | 237-302 | `iptables` check + Docker restart | 2+ roles |
| 11. Compose up | 335-373 | `docker compose up` with drift detection | 4+ roles |
| 12. Wait for port | verify.yml | `wait_for` | All roles |
| 13. Health verification | verify.yml | `uri` + `assert` | All roles |

Phase 7 (OpenBao) was already extracted into `common/tasks/openbao_compose_env.yml` — proving the pattern works. This ADR extends the same approach to phases 1-6 and 8-11.

### The cost of duplication

When a cross-cutting fix is needed (e.g., adding a retry to `docker compose pull`, or fixing the Docker NAT chain recovery to handle a new edge case), the fix must be applied to 40+ files. This has led to:

- The NAT chain recovery logic exists in only 2 roles today — most roles don't have it and silently fail when Docker networking breaks.
- Image pull retry counts vary: some roles retry 5 times, others 3, others don't retry at all.
- Secret generation uses `openssl rand -hex 32` in some roles and `openssl rand -base64 24` in others, with no documentation of why.

## Decision

Create **four new shared task files** in the `common` role. Each handles one discrete phase of the service lifecycle. Runtime roles include them with `include_role` / `include_tasks` and pass service-specific parameters.

### File locations

All new files go under `collections/ansible_collections/lv3/platform/roles/common/tasks/`:

```
common/tasks/check_local_secrets.yml      — Phase 2
common/tasks/manage_service_secrets.yml    — Phases 4-6
common/tasks/docker_compose_converge.yml   — Phases 9-11
common/tasks/verify_service_health.yml     — Phases 12-13 (see also ADR 0364)
```

Phase 1 (input validation) is already handled by `common/tasks/assert_vars.yml`.
Phase 3 (directories) is already handled by `common/tasks/directory_tree.yml`.
Phase 7 (OpenBao) is already handled by `common/tasks/openbao_compose_env.yml`.
Phase 8 (render templates) remains in each role — it's role-specific by nature.

### Task file 1: `check_local_secrets.yml`

**Purpose:** Check that required secret files exist on the Ansible control machine before deploying to the remote host. Fail early with actionable guidance if a prerequisite hasn't been converged.

**Input variables (all required):**

```yaml
common_check_local_secrets_files:
  # List of dicts, each with:
  #   path: absolute path to the secret file on the control machine
  #   description: human-readable name for error messages
  #   prerequisite: what to converge to create this file
  - path: "{{ directus_database_password_local_file }}"
    description: "Directus database password"
    prerequisite: "Converge directus_postgres before deploying Directus"
  - path: "{{ directus_keycloak_client_secret_local_file }}"
    description: "Directus Keycloak client secret"
    prerequisite: "Converge the Keycloak runtime before deploying Directus"
```

**Exact implementation:**

```yaml
---
- name: Validate check_local_secrets inputs
  ansible.builtin.assert:
    that:
      - common_check_local_secrets_files | length > 0
    fail_msg: "common.check_local_secrets requires at least one secret file definition."
    quiet: true

- name: Check whether required secret files exist on the control machine
  ansible.builtin.stat:
    path: "{{ item.path }}"
  delegate_to: localhost
  become: false
  register: common_check_local_secrets_results
  loop: "{{ common_check_local_secrets_files }}"
  loop_control:
    label: "{{ item.description }}"

- name: Fail if any required secret file is missing on the control machine
  ansible.builtin.fail:
    msg: >-
      {{ item.item.path }} is missing on the control machine.
      {{ item.item.prerequisite }}.
  when: not item.stat.exists
  loop: "{{ common_check_local_secrets_results.results }}"
  loop_control:
    label: "{{ item.item.description }}"
```

**How a runtime role uses it:**

```yaml
- name: Check Directus prerequisites on the control machine
  ansible.builtin.include_role:
    name: lv3.platform.common
    tasks_from: check_local_secrets
  vars:
    common_check_local_secrets_files:
      - path: "{{ directus_database_password_local_file }}"
        description: "Directus database password"
        prerequisite: "Converge directus_postgres before deploying Directus"
      - path: "{{ directus_keycloak_client_secret_local_file }}"
        description: "Directus Keycloak client secret"
        prerequisite: "Converge the Keycloak runtime before deploying Directus"
```

This replaces **6 tasks** (2 per secret file × 3 files = 6 tasks, ~40 lines) with **1 include** (~8 lines).

### Task file 2: `manage_service_secrets.yml`

**Purpose:** Idempotently generate secrets on the remote host, read them back, and mirror them to the control machine. Combines phases 4, 5, and 6.

**Input variables:**

```yaml
common_manage_service_secrets_generate:
  # List of secrets to generate on the remote host.
  # Each has: path (remote), command (shell command to generate), label (for logs)
  - path: "{{ directus_key_remote_file }}"
    command: "openssl rand -hex 32"
    label: "directus-key"
  - path: "{{ directus_secret_remote_file }}"
    command: "openssl rand -hex 32"
    label: "directus-secret"
  - path: "{{ directus_admin_password_remote_file }}"
    command: "openssl rand -base64 24 | tr -d '\\n'"
    label: "directus-admin-password"

common_manage_service_secrets_read:
  # List of remote paths to slurp. Order matters — results are indexed positionally.
  - "{{ directus_key_remote_file }}"
  - "{{ directus_secret_remote_file }}"
  - "{{ directus_admin_password_remote_file }}"

common_manage_service_secrets_mirror:
  # List of dicts: dest (local path), content_index (index into the read results)
  - dest: "{{ directus_key_local_file }}"
    content_index: 0
  - dest: "{{ directus_secret_local_file }}"
    content_index: 1
  - dest: "{{ directus_admin_password_local_file }}"
    content_index: 2

common_manage_service_secrets_local_artifact_dir: "{{ directus_local_artifact_dir }}"

# Output variable name — the task sets this fact with all decoded secrets
common_manage_service_secrets_fact_name: "directus_decoded_secrets"
```

**Exact implementation:**

```yaml
---
- name: Validate manage_service_secrets inputs
  ansible.builtin.assert:
    that:
      - common_manage_service_secrets_generate | length > 0 or common_manage_service_secrets_read | length > 0
    fail_msg: "common.manage_service_secrets requires at least one secret to generate or read."
    quiet: true

- name: Generate secrets idempotently on the remote host
  ansible.builtin.shell: |
    set -euo pipefail
    if [ ! -s "{{ item.path }}" ]; then
      umask 077
      {{ item.command }} > "{{ item.path }}"
      echo changed
    fi
  args:
    executable: /bin/bash
  loop: "{{ common_manage_service_secrets_generate }}"
  loop_control:
    label: "{{ item.label }}"
  register: common_manage_service_secrets_gen_results
  changed_when: "'changed' in common_manage_service_secrets_gen_results.stdout"
  no_log: true
  when: common_manage_service_secrets_generate | length > 0

- name: Read secrets from the remote host
  ansible.builtin.slurp:
    src: "{{ item }}"
  register: common_manage_service_secrets_read_results
  loop: "{{ common_manage_service_secrets_read }}"
  no_log: true
  when: common_manage_service_secrets_read | length > 0

- name: Record decoded secrets as a fact
  ansible.builtin.set_fact:
    "{{ common_manage_service_secrets_fact_name }}": >-
      {{
        common_manage_service_secrets_read_results.results
        | map(attribute='content')
        | map('b64decode')
        | map('trim')
        | list
      }}
  no_log: true
  when: common_manage_service_secrets_read | length > 0

- name: Ensure the local artifact directory exists
  ansible.builtin.file:
    path: "{{ common_manage_service_secrets_local_artifact_dir }}"
    state: directory
    mode: "0700"
  delegate_to: localhost
  become: false
  when: common_manage_service_secrets_mirror | length > 0

- name: Mirror secrets to the control machine
  ansible.builtin.copy:
    dest: "{{ item.dest }}"
    content: "{{ vars[common_manage_service_secrets_fact_name][item.content_index] }}\n"
    mode: "0600"
  delegate_to: localhost
  become: false
  loop: "{{ common_manage_service_secrets_mirror }}"
  loop_control:
    label: "{{ item.dest | basename }}"
  no_log: true
  when: common_manage_service_secrets_mirror | length > 0
```

**How a runtime role uses it:**

```yaml
- name: Manage Directus runtime secrets
  ansible.builtin.include_role:
    name: lv3.platform.common
    tasks_from: manage_service_secrets
  vars:
    common_manage_service_secrets_generate:
      - path: "{{ directus_key_remote_file }}"
        command: "openssl rand -hex 32"
        label: "directus-key"
      - path: "{{ directus_secret_remote_file }}"
        command: "openssl rand -hex 32"
        label: "directus-secret"
    common_manage_service_secrets_read:
      - "{{ directus_key_remote_file }}"
      - "{{ directus_secret_remote_file }}"
    common_manage_service_secrets_mirror:
      - dest: "{{ directus_key_local_file }}"
        content_index: 0
      - dest: "{{ directus_secret_local_file }}"
        content_index: 1
    common_manage_service_secrets_local_artifact_dir: "{{ directus_local_artifact_dir }}"
    common_manage_service_secrets_fact_name: "directus_decoded_secrets"
```

This replaces **~50 lines** (generate + slurp + set_fact + mkdir + copy) with **~20 lines** of configuration.

### Task file 3: `docker_compose_converge.yml`

**Purpose:** Pull images, recover Docker networking if broken, start the compose stack with drift detection, and optionally force-recreate.

**Input variables:**

```yaml
common_docker_compose_converge_compose_file: "{{ directus_compose_file }}"
common_docker_compose_converge_site_dir: "{{ directus_site_dir }}"
common_docker_compose_converge_service_name: "directus"

# Optional: list of registered template results to check for changes
common_docker_compose_converge_template_results: []
  # - "{{ directus_env_template }}"
  # - "{{ directus_compose_template }}"

# Optional: port to probe before deciding on force-recreate
common_docker_compose_converge_health_port: "{{ directus_internal_port | default(0) }}"
common_docker_compose_converge_health_url: ""  # e.g., "http://127.0.0.1:8055/server/health"

# Optional: specific service name to force-recreate (defaults to service_name)
common_docker_compose_converge_force_recreate_service: ""

# Pull retry configuration
common_docker_compose_converge_pull_retries: 5
common_docker_compose_converge_pull_delay: 5
```

**Exact implementation:**

```yaml
---
- name: Validate docker_compose_converge inputs
  ansible.builtin.assert:
    that:
      - common_docker_compose_converge_compose_file | length > 0
      - common_docker_compose_converge_site_dir | length > 0
      - common_docker_compose_converge_service_name | length > 0
    fail_msg: "common.docker_compose_converge requires compose_file, site_dir, and service_name."
    quiet: true

- name: "Pull images for {{ common_docker_compose_converge_service_name }}"
  ansible.builtin.command:
    argv:
      - docker
      - compose
      - --file
      - "{{ common_docker_compose_converge_compose_file }}"
      - pull
  args:
    chdir: "{{ common_docker_compose_converge_site_dir }}"
  register: common_dcc_pull
  retries: "{{ common_docker_compose_converge_pull_retries }}"
  delay: "{{ common_docker_compose_converge_pull_delay }}"
  until: common_dcc_pull.rc == 0
  changed_when: >-
    'Pulling' in common_dcc_pull.stdout
    or 'Downloaded newer image' in common_dcc_pull.stdout
    or 'Pull complete' in common_dcc_pull.stdout

- name: "Check Docker NAT chain before {{ common_docker_compose_converge_service_name }} startup"
  ansible.builtin.command:
    argv:
      - iptables
      - -t
      - nat
      - -S
      - DOCKER
  register: common_dcc_nat_chain
  changed_when: false
  failed_when: false

- name: Restore Docker networking when the NAT chain is missing
  ansible.builtin.service:
    name: docker
    state: restarted
  when: common_dcc_nat_chain.rc != 0

- name: Recheck Docker NAT chain after recovery
  ansible.builtin.command:
    argv:
      - iptables
      - -t
      - nat
      - -S
      - DOCKER
  register: common_dcc_nat_chain_recheck
  changed_when: false
  failed_when: common_dcc_nat_chain_recheck.rc not in [0, 1]
  retries: 10
  delay: 2
  until: common_dcc_nat_chain_recheck.rc == 0
  when: common_dcc_nat_chain.rc != 0

- name: Wait for Docker daemon after networking recovery
  ansible.builtin.command:
    argv:
      - docker
      - info
      - --format
      - "{{ '{{.ServerVersion}}' }}"
  register: common_dcc_docker_info
  changed_when: false
  retries: 10
  delay: 2
  until: common_dcc_docker_info.rc == 0
  when: common_dcc_nat_chain.rc != 0

- name: Assert Docker NAT chain is present
  ansible.builtin.assert:
    that:
      - common_dcc_nat_chain.rc == 0 or (common_dcc_nat_chain_recheck.rc | default(1)) == 0
    fail_msg: "Docker is running but the NAT DOCKER chain is missing; published ports will fail."

- name: "Check {{ common_docker_compose_converge_service_name }} local port before startup"
  ansible.builtin.wait_for:
    host: 127.0.0.1
    port: "{{ common_docker_compose_converge_health_port }}"
    delay: 0
    timeout: 1
  register: common_dcc_port_probe
  changed_when: false
  failed_when: false
  when: common_docker_compose_converge_health_port | int > 0

- name: "Check {{ common_docker_compose_converge_service_name }} health before startup"
  ansible.builtin.uri:
    url: "{{ common_docker_compose_converge_health_url }}"
    method: GET
    status_code: 200
  register: common_dcc_health_probe
  changed_when: false
  failed_when: false
  when: common_docker_compose_converge_health_url | length > 0

- name: Determine whether force-recreate is needed
  ansible.builtin.set_fact:
    common_dcc_force_recreate: >-
      {{
        common_dcc_nat_chain.rc != 0
        or (common_docker_compose_converge_template_results | selectattr('changed', 'defined') | selectattr('changed') | list | length > 0)
        or (common_dcc_pull.changed | default(false))
        or (common_dcc_port_probe.failed | default(false))
        or (common_dcc_health_probe.status | default(0)) != 200
      }}

- name: "Start {{ common_docker_compose_converge_service_name }} stack"
  ansible.builtin.command:
    argv:
      - docker
      - compose
      - --file
      - "{{ common_docker_compose_converge_compose_file }}"
      - up
      - -d
      - --remove-orphans
  args:
    chdir: "{{ common_docker_compose_converge_site_dir }}"
  register: common_dcc_up
  changed_when: >-
    'Creating' in common_dcc_up.stdout
    or 'Recreating' in common_dcc_up.stdout
    or 'Starting' in common_dcc_up.stdout
  when: not common_dcc_force_recreate

- name: "Force-recreate {{ common_docker_compose_converge_service_name }} after drift or Docker recovery"
  ansible.builtin.command:
    argv:
      - docker
      - compose
      - --file
      - "{{ common_docker_compose_converge_compose_file }}"
      - up
      - -d
      - --force-recreate
      - --no-deps
      - "{{ common_docker_compose_converge_force_recreate_service | default(common_docker_compose_converge_service_name) }}"
  args:
    chdir: "{{ common_docker_compose_converge_site_dir }}"
  register: common_dcc_force_up
  changed_when: >-
    'Creating' in common_dcc_force_up.stdout
    or 'Recreating' in common_dcc_force_up.stdout
    or 'Starting' in common_dcc_force_up.stdout
  when: common_dcc_force_recreate
```

**How a runtime role uses it:**

```yaml
- name: Converge the Directus Docker stack
  ansible.builtin.include_role:
    name: lv3.platform.common
    tasks_from: docker_compose_converge
  vars:
    common_docker_compose_converge_compose_file: "{{ directus_compose_file }}"
    common_docker_compose_converge_site_dir: "{{ directus_site_dir }}"
    common_docker_compose_converge_service_name: directus
    common_docker_compose_converge_template_results:
      - "{{ directus_env_template }}"
      - "{{ directus_compose_template }}"
    common_docker_compose_converge_health_port: "{{ directus_internal_port }}"
    common_docker_compose_converge_health_url: "{{ directus_internal_base_url }}{{ directus_health_path }}"
```

This replaces **~70 lines** (pull + NAT recovery + compose up + force-recreate) with **~12 lines** of configuration.

### Migration strategy

**Do NOT migrate all 40 roles at once.** Follow this phased approach:

#### Phase 1: Create the shared task files (1 commit)

Create all three new task files in `common/tasks/`. Add corresponding default values in `common/defaults/main.yml`. Run `make validate-yaml` and `make validate-ansible-syntax`.

```bash
git add collections/ansible_collections/lv3/platform/roles/common/tasks/check_local_secrets.yml
git add collections/ansible_collections/lv3/platform/roles/common/tasks/manage_service_secrets.yml
git add collections/ansible_collections/lv3/platform/roles/common/tasks/docker_compose_converge.yml
git add collections/ansible_collections/lv3/platform/roles/common/defaults/main.yml
git commit -m "feat(common): add shared service lifecycle task includes — ADR 0363"
```

#### Phase 2: Migrate `directus_runtime` as reference implementation (1 commit)

Rewrite `directus_runtime/tasks/main.yml` to use the shared includes. The resulting file should be significantly shorter. Compare the Ansible verbose output (`-vvv`) before and after to ensure identical behaviour.

```bash
# Before migration — capture verbose output:
ansible-playbook playbooks/directus.yml -e env=production -l docker-runtime-lv3 --check -vvv 2>&1 | tee /tmp/directus-before.log

# After migration — compare:
ansible-playbook playbooks/directus.yml -e env=production -l docker-runtime-lv3 --check -vvv 2>&1 | tee /tmp/directus-after.log

diff /tmp/directus-before.log /tmp/directus-after.log
```

#### Phase 3: Migrate remaining roles in batches of 5-8

Group by similarity. Suggested batch order:

1. **Batch A** (simplest — follow directus pattern exactly): `outline_runtime`, `semaphore_runtime`, `grist_runtime`, `langfuse_runtime`, `label_studio_runtime`
2. **Batch B** (similar but with extra secrets): `gitea_runtime`, `keycloak_runtime`, `nextcloud_runtime`, `mattermost_runtime`, `n8n_runtime`
3. **Batch C** (more complex compose stacks): `dify_runtime`, `plane_runtime`, `superset_runtime`, `windmill_runtime`, `temporal_runtime`
4. **Batch D** (remaining): all other `*_runtime` roles

After each batch:
```bash
make validate-yaml
make validate-ansible-syntax
# Optionally run a --check against one service in the batch
```

### What NOT to do

- Do **not** create a mega-role that replaces all runtime roles. Each runtime role retains its identity, templates, and service-specific logic. The shared includes handle only the generic lifecycle phases.
- Do **not** force all roles to use all three includes. If a role doesn't generate secrets (e.g., `dozzle_runtime`), it simply skips `manage_service_secrets`.
- Do **not** change the variable naming convention (`<service>_*`). The shared includes use their own `common_*` namespace; the calling role maps its variables into that namespace.
- Do **not** remove the service-specific `tasks/main.yml` files. They remain as the orchestration layer that calls the shared includes in the correct order with the correct parameters.

## Consequences

**Positive:**
- The Docker NAT chain recovery logic becomes available to **all** runtime roles, not just the 2 that currently have it. This prevents silent networking failures on Docker daemon restart.
- Image pull retries are standardised at 5 retries / 5s delay across all roles.
- Secret generation/mirroring follows a single audited implementation. A security fix (e.g., switching from `openssl rand` to a different CSPRNG) propagates to all roles.
- New service onboarding: a `tasks/main.yml` for a new runtime role shrinks from ~150 lines to ~50-60 lines.

**Negative / Trade-offs:**
- Indirection: debugging a failed converge requires understanding that `docker_compose_converge.yml` is being included from `common`. Task names include the service name to aid diagnosis.
- Variable mapping: callers must map their `<service>_*` variables into `common_*` variables. This is verbose but explicit.
- Ansible `include_role` has performance implications — each include adds overhead. For 3 includes per role this is negligible (< 1 second total).

## Implementation plan

1. Create `common/tasks/check_local_secrets.yml` with exact implementation above
2. Create `common/tasks/manage_service_secrets.yml` with exact implementation above
3. Create `common/tasks/docker_compose_converge.yml` with exact implementation above
4. Add default values for all `common_*` variables in `common/defaults/main.yml`
5. Migrate `directus_runtime` — verify identical behaviour
6. Migrate remaining roles in batches (see Phase 3 above)

## Depends on

- ADR 0021 (Docker Runtime) — compose lifecycle
- ADR 0063 (OpenBao Integration) — `openbao_compose_env` is the precedent for this pattern

## Related

- ADR 0361 (Compose Macro Library) — handles template-level duplication; this ADR handles task-level duplication
- ADR 0364 (Parameterized Verify Tasks) — handles the verify.yml duplication
- ADR 0359 (Declarative PostgreSQL Client Registry) — same "extract shared role from N identical roles" pattern
