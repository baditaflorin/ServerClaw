# ADR 0371: Parameterized Service Verification Tasks

- **Date**: 2026-04-06
- **Status**: Proposed
- **Deciders**: platform team
- **Concern**: platform, dry
- **Tags**: ansible, verification, healthcheck, dry

## Context

~30 runtime roles contain a `tasks/verify.yml` file with near-identical verification logic. The `directus_runtime/tasks/verify.yml` (68 lines) is representative:

```yaml
# 1. Wait for TCP port
- name: Wait for the Directus runtime to listen locally
  ansible.builtin.wait_for:
    host: 127.0.0.1
    port: "{{ directus_internal_port }}"
    delay: 0
    timeout: 300

# 2. HTTP health endpoint
- name: Verify the Directus health endpoint
  ansible.builtin.uri:
    url: "{{ directus_internal_base_url }}{{ directus_health_path }}"
    method: GET
    status_code: 200
    return_content: true
  register: directus_verify_health
  retries: 36
  delay: 5
  until: directus_verify_health.status == 200
  changed_when: false

# 3. Assert health response
- name: Assert the Directus health payload reports ok
  ansible.builtin.assert:
    that:
      - directus_verify_health.json.status == "ok"
    fail_msg: "Directus answered locally, but /server/health did not report status=ok."
```

The same 3-step pattern (wait for port → GET health endpoint with retries → assert response content) appears in `semaphore_runtime`, `outline_runtime`, `gitea_runtime`, `keycloak_runtime`, `woodpecker_runtime`, `portainer_runtime`, `flagsmith_runtime`, `glitchtip_runtime`, `n8n_runtime`, `nextcloud_runtime`, `mattermost_runtime`, `plausible_runtime`, `superset_runtime`, `windmill_runtime`, `typesense_runtime`, and many more.

### Variations across roles

| Aspect | Directus | Semaphore | Outline | Portainer |
|---|---|---|---|---|
| Port timeout | 300s | 180s | 300s | 120s |
| Health retries | 36 | 18 | 18 | 18 |
| Health delay | 5s | 5s | 5s | 10s |
| Response check | `json.status == "ok"` | `status == 200` | `status == 200` | `json.status == 1` |
| Extra checks | ping + OpenAPI | none | none | container running |

All variations can be expressed as parameters.

## Decision

Create a shared `verify_service_health.yml` task file in the `common` role that handles all verification patterns through parameters.

### File location

```
collections/ansible_collections/lv3/platform/roles/common/tasks/verify_service_health.yml
```

### Input variables

```yaml
# Required
common_verify_service_name: "directus"         # For task names and log messages
common_verify_port: 8055                        # TCP port to wait for

# Optional — TCP wait
common_verify_port_host: "127.0.0.1"           # Host to probe (default: 127.0.0.1)
common_verify_port_timeout: 300                 # Seconds to wait for port (default: 300)

# Optional — HTTP health check
common_verify_health_url: ""                    # Full URL (e.g., http://127.0.0.1:8055/server/health)
                                                 # If empty, skip HTTP verification
common_verify_health_retries: 36                # Max retries (default: 36)
common_verify_health_delay: 5                   # Seconds between retries (default: 5)
common_verify_health_status_code: 200           # Expected HTTP status (default: 200)

# Optional — response body assertions
common_verify_health_assertions: []
  # List of Jinja2 expressions to assert against the response.
  # The response is available as `common_verify_health_response`.
  # Examples:
  #   - "common_verify_health_response.json.status == 'ok'"
  #   - "common_verify_health_response.content | trim == 'pong'"
  #   - "'paths' in common_verify_health_response.json"

common_verify_health_assertion_msg: ""          # Custom fail message for assertions

# Optional — additional endpoint checks
common_verify_extra_endpoints: []
  # List of additional endpoints to verify after the primary health check.
  # Each entry:
  #   url: full URL
  #   status_code: expected status (default: 200)
  #   retries: max retries (default: 18)
  #   delay: seconds between retries (default: 5)
  #   assertions: list of Jinja2 expressions (optional)
  #   assertion_msg: custom fail message (optional)
```

### Exact implementation

```yaml
---
- name: "Wait for {{ common_verify_service_name }} to listen on port {{ common_verify_port }}"
  ansible.builtin.wait_for:
    host: "{{ common_verify_port_host | default('127.0.0.1') }}"
    port: "{{ common_verify_port }}"
    delay: 0
    timeout: "{{ common_verify_port_timeout | default(300) }}"

- name: "Verify {{ common_verify_service_name }} health endpoint"
  ansible.builtin.uri:
    url: "{{ common_verify_health_url }}"
    method: GET
    status_code: "{{ common_verify_health_status_code | default(200) }}"
    return_content: true
  register: common_verify_health_response
  retries: "{{ common_verify_health_retries | default(36) }}"
  delay: "{{ common_verify_health_delay | default(5) }}"
  until: common_verify_health_response.status == (common_verify_health_status_code | default(200) | int)
  changed_when: false
  when: (common_verify_health_url | default('')) | length > 0

- name: "Assert {{ common_verify_service_name }} health response"
  ansible.builtin.assert:
    that: "{{ common_verify_health_assertions }}"
    fail_msg: >-
      {{ common_verify_health_assertion_msg | default(
        common_verify_service_name ~ ' health endpoint responded but assertions failed.'
      ) }}
  when:
    - (common_verify_health_url | default('')) | length > 0
    - (common_verify_health_assertions | default([])) | length > 0

- name: "Verify {{ common_verify_service_name }} extra endpoints"
  ansible.builtin.include_tasks: verify_service_health_extra.yml
  loop: "{{ common_verify_extra_endpoints | default([]) }}"
  loop_control:
    loop_var: common_verify_extra_endpoint
    label: "{{ common_verify_extra_endpoint.url }}"
  when: (common_verify_extra_endpoints | default([])) | length > 0
```

### Helper file: `verify_service_health_extra.yml`

```yaml
---
- name: "Verify {{ common_verify_service_name }} endpoint {{ common_verify_extra_endpoint.url }}"
  ansible.builtin.uri:
    url: "{{ common_verify_extra_endpoint.url }}"
    method: GET
    status_code: "{{ common_verify_extra_endpoint.status_code | default(200) }}"
    return_content: true
  register: common_verify_extra_response
  retries: "{{ common_verify_extra_endpoint.retries | default(18) }}"
  delay: "{{ common_verify_extra_endpoint.delay | default(5) }}"
  until: common_verify_extra_response.status == (common_verify_extra_endpoint.status_code | default(200) | int)
  changed_when: false

- name: "Assert {{ common_verify_service_name }} endpoint {{ common_verify_extra_endpoint.url }}"
  ansible.builtin.assert:
    that: "{{ common_verify_extra_endpoint.assertions }}"
    fail_msg: >-
      {{ common_verify_extra_endpoint.assertion_msg | default(
        common_verify_service_name ~ ' extra endpoint ' ~ common_verify_extra_endpoint.url ~ ' assertions failed.'
      ) }}
  when: (common_verify_extra_endpoint.assertions | default([])) | length > 0
```

### Usage examples

**Simple service (most roles):**

```yaml
# In <service>_runtime/tasks/verify.yml
---
- name: Verify the {{ service_name }} runtime
  ansible.builtin.include_role:
    name: lv3.platform.common
    tasks_from: verify_service_health
  vars:
    common_verify_service_name: semaphore
    common_verify_port: "{{ semaphore_port }}"
    common_verify_health_url: "{{ semaphore_internal_base_url }}/api/ping"
    common_verify_health_assertions:
      - "common_verify_health_response.content | trim == 'pong'"
```

**Complex service (Directus — port + health + ping + OpenAPI):**

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

### Migration procedure

For each `*_runtime/tasks/verify.yml`:

1. Read the existing verify.yml and identify which checks it performs (port wait, health URL, assertions, extra endpoints).
2. Rewrite the file to use a single `include_role` call with the appropriate parameters.
3. **Keep the role-level `tasks/verify.yml` file** — do not delete it. It becomes a thin wrapper that calls the shared include. This preserves the existing `import_tasks: verify.yml` call sites in `tasks/main.yml`.
4. Run `make validate-ansible-syntax`.
5. Test with `--check` against the target host.

### What NOT to do

- Do **not** delete `tasks/verify.yml` files from individual roles. They serve as the role's verification entry point and may contain service-specific checks beyond the standard pattern.
- Do **not** add container-running checks (docker ps) to this shared task. That belongs in a separate specialized check for roles that need it.
- Do **not** change retry/delay values during migration. Match the existing values exactly, then standardize in a follow-up.

## Consequences

**Positive:**
- Eliminates ~30 near-identical verify.yml files (total ~600 lines of duplication).
- Standardises verification patterns — new roles get robust verification by default.
- Retry and timeout values become explicitly documented parameters rather than silently varying magic numbers.

**Negative / Trade-offs:**
- The assertion mechanism uses Jinja2 expressions as strings, which is less IDE-friendly than direct `assert` blocks. Trade-off accepted for the DRY benefit.
- Roles with highly custom verification (e.g., database schema checks) still need custom code after the shared include.

## Implementation plan

1. Create `common/tasks/verify_service_health.yml` and `common/tasks/verify_service_health_extra.yml`
2. Add default values in `common/defaults/main.yml`
3. Migrate `directus_runtime/tasks/verify.yml` as reference implementation
4. Migrate simple roles (port + health only): semaphore, dozzle, portainer, typesense
5. Migrate medium roles (health + assertions): outline, gitea, n8n, nextcloud
6. Migrate complex roles (multiple endpoints): directus, flagsmith, keycloak

## Depends on

None — this is a self-contained addition to the `common` role.

## Related

- ADR 0370 (Service Lifecycle Task Includes) — handles the main.yml duplication; this ADR handles verify.yml
- ADR 0289 (Health Probe Catalog) — defines the health endpoints this ADR verifies
