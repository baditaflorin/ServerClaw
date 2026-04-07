# ADR 0368: Docker Compose Jinja2 Macro Library

- **Date**: 2026-04-06
- **Status**: Proposed
- **Deciders**: platform team
- **Concern**: platform, dry
- **Tags**: docker, jinja2, templates, dry, macros

## Context

The platform manages ~60 Docker Compose Jinja2 templates across runtime roles under `collections/ansible_collections/lv3/platform/roles/*/templates/docker-compose.yml.j2`. These templates contain massive boilerplate duplication:

| Repeated block | Files affected | Lines per occurrence |
|---|---|---|
| OpenBao agent sidecar service | 35/60 (58%) | 20-25 lines |
| Redis service + healthcheck | 12+ | 15-20 lines |
| HTTP healthcheck (wget/curl/python — inconsistent) | 15+ | 8-10 lines |
| `logging:` driver configuration | 50+ | 4-5 lines (values drift: `10m/3` vs `50m/5` vs `20m/3`) |
| `networks: lv3_service_net: external: true` | 60/60 | 3 lines |
| `restart: unless-stopped` | 58/60 | 1 line |
| `extra_hosts` hairpin NAT entries | 15+ | 3-8 lines (manually maintained, stale entries) |

### Concrete examples of the problem

**OpenBao sidecar** — the following ~22 lines are copy-pasted verbatim into 35 compose templates, differing only in the variable prefix (`directus_`, `gitea_`, `keycloak_`, …):

```yaml
  openbao-agent:
    image: {{ directus_openbao_agent_image }}
    container_name: {{ directus_openbao_agent_container_name }}
    user: "0:0"
    environment:
      BAO_SKIP_DROP_ROOT: "true"
    command:
      - agent
      - -config=/openbao-agent/agent.hcl
    network_mode: host
    restart: unless-stopped
    healthcheck:
      test:
        - CMD-SHELL
        - test -s {{ directus_env_file }}
      interval: 10s
      timeout: 3s
      retries: 12
    volumes:
      - {{ directus_openbao_agent_dir }}:/openbao-agent:ro
      - {{ directus_env_file | dirname }}:{{ directus_env_file | dirname }}
```

**Logging config** — drift has introduced inconsistency with no rationale:
- `dify_runtime`: `max-size: "50m"`, `max-file: "5"`
- `directus_runtime`: `max-size: "10m"`, `max-file: "3"`
- `plausible_runtime`: `max-size: "20m"`, `max-file: "3"`

**Hairpin NAT** — each compose file that needs internal-domain routing manually maintains `extra_hosts`, leading to stale entries when IPs change.

## Decision

Create a shared **Jinja2 macro library** at `collections/ansible_collections/lv3/platform/roles/common/templates/compose_macros.j2`. Each compose template imports from this library and calls macros instead of repeating boilerplate.

### File location

```
collections/ansible_collections/lv3/platform/roles/common/templates/compose_macros.j2
```

This file lives inside the `common` role so that all runtime roles (which already depend on `common`) can access it via Jinja2's `{% import %}` directive.

### Macro definitions

The file **must** contain the following macros. Each macro is documented here with its exact signature, parameters, default values, and the YAML it must emit. Implementers must reproduce this output exactly — do not deviate from the YAML structure shown below.

#### Macro 1: `openbao_sidecar(prefix)`

Emits the OpenBao agent sidecar service block. The `prefix` parameter is the role variable prefix (e.g., `directus`, `gitea`).

**Signature:**
```jinja2
{% macro openbao_sidecar(prefix) %}
```

**Parameters:**
- `prefix` (string, required): The Ansible variable prefix for the service. Used to resolve `{{ vars[prefix + '_openbao_agent_image'] }}`, `{{ vars[prefix + '_openbao_agent_container_name'] }}`, `{{ vars[prefix + '_env_file'] }}`, `{{ vars[prefix + '_openbao_agent_dir'] }}`.

**Emitted YAML:**
```yaml
  openbao-agent:
    image: {{ vars[prefix + '_openbao_agent_image'] }}
    container_name: {{ vars[prefix + '_openbao_agent_container_name'] }}
    user: "0:0"
    environment:
      BAO_SKIP_DROP_ROOT: "true"
    command:
      - agent
      - -config=/openbao-agent/agent.hcl
    network_mode: host
    restart: unless-stopped
    healthcheck:
      test:
        - CMD-SHELL
        - test -s {{ vars[prefix + '_env_file'] }}
      interval: 10s
      timeout: 3s
      retries: 12
    volumes:
      - {{ vars[prefix + '_openbao_agent_dir'] }}:/openbao-agent:ro
      - {{ vars[prefix + '_env_file'] | dirname }}:{{ vars[prefix + '_env_file'] | dirname }}
```

**Important:** The `vars[prefix + '...']` pattern uses Ansible's `vars` dictionary for dynamic variable access. This is well-supported in Jinja2 templates rendered by Ansible. Do **not** use `hostvars[inventory_hostname]` — use `vars` directly.

#### Macro 2: `redis_service(prefix, requirepass=true, use_valkey=false, append_only=true)`

Emits a Redis (or Valkey) service block with healthcheck.

**Signature:**
```jinja2
{% macro redis_service(prefix, requirepass=true, use_valkey=false, append_only=true) %}
```

**Parameters:**
- `prefix` (string, required): Resolves `{{ vars[prefix + '_redis_image'] }}`, `{{ vars[prefix + '_redis_container_name'] }}`, `{{ vars[prefix + '_redis_password'] }}`, `{{ vars[prefix + '_redis_dir'] }}`.
- `requirepass` (bool, default `true`): Whether Redis requires authentication.
- `use_valkey` (bool, default `false`): Use `valkey-server` binary instead of `redis-server`.
- `append_only` (bool, default `true`): Enable AOF persistence.

**Emitted YAML (when `requirepass=true`, `use_valkey=false`, `append_only=true`):**
```yaml
  redis:
    image: {{ vars[prefix + '_redis_image'] }}
    container_name: {{ vars[prefix + '_redis_container_name'] }}
    restart: unless-stopped
    command:
      - redis-server
      - --requirepass
      - {{ vars[prefix + '_redis_password'] }}
      - --appendonly
      - "yes"
    healthcheck:
      test:
        - CMD-SHELL
        - redis-cli -a "{{ vars[prefix + '_redis_password'] }}" ping | grep -q PONG
      interval: 5s
      timeout: 5s
      retries: 10
    volumes:
      - {{ vars[prefix + '_redis_dir'] }}:/data
{{ logging() }}
```

#### Macro 3: `healthcheck(type, port, path="/", interval=10, timeout=5, retries=12, start_period=None)`

Emits a `healthcheck:` block. Standardises the three ad-hoc patterns (wget, curl, python) into one controlled interface.

**Signature:**
```jinja2
{% macro healthcheck(type, port, path="/", interval=10, timeout=5, retries=12, start_period=None) %}
```

**Parameters:**
- `type` (string, required): One of `"wget"`, `"curl"`, `"pg_isready"`, `"redis"`, `"file_exists"`. Determines the test command.
- `port` (int, required): The container-internal port.
- `path` (string, default `"/"`): HTTP path for wget/curl types.
- `interval`, `timeout`, `retries`, `start_period` (int/None): Timing parameters.

**Emitted YAML examples:**

For `type="wget"`:
```yaml
    healthcheck:
      test:
        - CMD-SHELL
        - wget --no-verbose --tries=1 --spider http://127.0.0.1:{{ port }}{{ path }} || exit 1
      interval: {{ interval }}s
      timeout: {{ timeout }}s
      retries: {{ retries }}
```

For `type="curl"`:
```yaml
    healthcheck:
      test:
        - CMD-SHELL
        - curl -fsS http://127.0.0.1:{{ port }}{{ path }} > /dev/null || exit 1
      interval: {{ interval }}s
      timeout: {{ timeout }}s
      retries: {{ retries }}
```

For `type="pg_isready"` — `port` and `path` are repurposed: `port` is the Postgres port, `path` is used as the database name:
```yaml
    healthcheck:
      test:
        - CMD-SHELL
        - pg_isready -U {{ path }} -d {{ path }}
      interval: {{ interval }}s
      timeout: {{ timeout }}s
      retries: {{ retries }}
```

#### Macro 4: `logging(max_size="10m", max_file="3")`

Emits a `logging:` block with the platform-standard defaults. This is the single source of truth for log rotation settings.

**Signature:**
```jinja2
{% macro logging(max_size="10m", max_file="3") %}
```

**Emitted YAML:**
```yaml
    logging:
      driver: json-file
      options:
        max-size: "{{ max_size }}"
        max-file: "{{ max_file }}"
```

#### Macro 5: `service_network()`

Emits the standard platform service network definition.

**Signature:**
```jinja2
{% macro service_network() %}
```

**Emitted YAML:**
```yaml
networks:
  lv3_service_net:
    external: true
```

#### Macro 6: `hairpin_hosts()`

Emits `extra_hosts` entries from a centrally managed variable `platform_hairpin_nat_hosts` (defined in `inventory/group_vars/platform.yml`). This eliminates manual per-service maintenance.

**Signature:**
```jinja2
{% macro hairpin_hosts() %}
```

**Emitted YAML:**
```yaml
    extra_hosts:
{% for entry in platform_hairpin_nat_hosts %}
      - "{{ entry.hostname }}:{{ entry.address }}"
{% endfor %}
```

**Requires** a new variable in `inventory/group_vars/platform.yml`:
```yaml
platform_hairpin_nat_hosts:
  - hostname: agents.lv3.org
    address: 10.10.10.92
  - hostname: dify.lv3.org
    address: 10.10.10.92
  - hostname: data.lv3.org
    address: 10.10.10.92
  # ... all internal domains that need hairpin NAT resolution
```

### How to import and use in a compose template

Every `docker-compose.yml.j2` file must add this import line at the very top of the file, before `---`:

```jinja2
{% from 'compose_macros.j2' import openbao_sidecar, redis_service, healthcheck, logging, service_network, hairpin_hosts %}
---
services:
  directus:
    image: {{ directus_image }}
    container_name: {{ directus_container_name }}
    restart: unless-stopped
    env_file:
      - {{ directus_env_file }}
{{ healthcheck(type="wget", port=directus_internal_port, path="/server/health") }}
{{ logging() }}
{{ hairpin_hosts() }}

{{ openbao_sidecar("directus") }}

{{ service_network() }}
```

### Ansible template lookup path

Ansible resolves `{% from %}` / `{% import %}` relative to the role's own `templates/` directory. Because the macros live in the `common` role, each consuming role must configure the Jinja2 search path. There are two approaches:

**Approach A (preferred):** Set `ansible_template_search_path` in the role's `defaults/main.yml`:
```yaml
# In every *_runtime role's defaults/main.yml, add:
<service>_template_search_path:
  - "{{ role_path }}/templates"
  - "{{ role_path }}/../../common/templates"
```

Then, in the role's `tasks/main.yml`, when calling `ansible.builtin.template`, the template module will search both the role's own templates and the common templates directory.

**Approach B (alternative):** Symlink `compose_macros.j2` into each role's `templates/` directory. This is simpler but requires maintaining symlinks.

**Decision:** Use Approach A. Do not use symlinks.

### Migration strategy

1. **Create the macro file** with all 6 macros.
2. **Add `platform_hairpin_nat_hosts`** to `inventory/group_vars/platform.yml` by consolidating all `extra_hosts` entries currently scattered across compose templates.
3. **Migrate one role** (start with `directus_runtime` as the reference implementation) — replace boilerplate with macro calls, verify the rendered output is byte-identical (except for logging standardisation).
4. **Migrate remaining roles** in batches of 5-10, verifying rendered output each time.
5. **Run `make validate-yaml`** after each batch to catch rendering errors.

### Verification procedure

After migrating each role:

```bash
# 1. Render the template locally to verify output
ansible -m template -a "src=collections/ansible_collections/lv3/platform/roles/<service>_runtime/templates/docker-compose.yml.j2 dest=/tmp/<service>-compose.yml" localhost

# 2. Compare with the previous known-good rendered output on the target host
# (SSH to the target and diff /opt/<service>/docker-compose.yml against /tmp/<service>-compose.yml)

# 3. Run the full syntax validation
make validate-yaml
```

## Consequences

**Positive:**
- Eliminates ~1,100+ lines of duplicated YAML across 60 templates.
- Logging configuration becomes consistent and centrally controlled — no more silent drift between `10m/3` and `50m/5`.
- Hairpin NAT entries are managed in one place; adding a new internal domain updates all services automatically.
- Healthcheck patterns are standardised; a security or performance fix (e.g., switching from `wget` to `curl` for a CVE) propagates to all services via one macro change.
- New service onboarding is faster — compose templates shrink from ~80-120 lines to ~30-50 lines of service-specific config.

**Negative / Trade-offs:**
- Macro import adds a Jinja2 search path dependency — each role must be able to find `compose_macros.j2` from the `common` role.
- Debugging rendered templates requires understanding the macro expansion. Mitigated by the verification procedure above.
- Macros must be kept backwards-compatible: changing a macro signature breaks all consuming templates in the same commit. Use optional parameters with defaults to extend macros.

## Implementation plan

1. Create `collections/ansible_collections/lv3/platform/roles/common/templates/compose_macros.j2` with all 6 macros
2. Add `platform_hairpin_nat_hosts` to `inventory/group_vars/platform.yml`
3. Migrate `directus_runtime` as reference implementation — verify byte-identical output
4. Migrate the 35 OpenBao sidecar users (highest duplication)
5. Migrate the 12 Redis service users
6. Migrate remaining compose templates for logging/network/healthcheck standardisation
7. Remove all inline `extra_hosts` blocks that are now served by `hairpin_hosts()`

## Depends on

- ADR 0021 (Docker Runtime) — compose template structure
- ADR 0063 (OpenBao Integration) — sidecar pattern this ADR extracts

## Related

- ADR 0370 (Service Lifecycle Task Includes) — extracts the Ansible task-level duplication that wraps these templates
- ADR 0373 (Service Registry) — the registry this ADR's `hairpin_hosts()` variable anticipates
