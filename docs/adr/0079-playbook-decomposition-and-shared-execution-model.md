# ADR 0079: Playbook Decomposition And Shared Execution Model

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The repository has 17+ playbooks. As new ADRs are implemented, the count will exceed 25. Several patterns have emerged that reduce maintainability:

- **monolithic plays** — `site.yml` imports all playbooks sequentially, giving no way to run a logical group (e.g. "all security services") without knowing which playbook files to list
- **duplicated pre_tasks blocks** — every playbook repeats the same preflight assertions (validate secrets, check SSH connectivity, assert environment variable), copy-pasted with minor variations
- **no environment-awareness** — playbooks hardcode `hosts: docker-runtime-lv3` without considering the staging topology (ADR 0072); running against staging requires manual `--limit` flags
- **no play-level tagging** — there is no consistent tagging strategy; operators cannot run `make live-apply tags=observability` to touch only monitoring-related services
- **no import graph** — it is unclear which playbooks must run before others; dependencies are implicit in the role ordering rather than declared

ADR 0062 addressed this at the role level. This ADR addresses it at the playbook level.

## Decision

We will restructure the playbook layer into a declared, composable, environment-aware execution model.

### Directory structure

```
playbooks/
  site.yml                    # Master import; always environment-aware
  groups/
    security.yml              # step-ca + OpenBao + Keycloak
    observability.yml         # Grafana + Loki + Tempo + GlitchTip + Uptime Kuma
    automation.yml            # Windmill + NATS + Mattermost
    data.yml                  # PostgreSQL
    access.yml                # NGINX edge + Tailscale + SSH
    communication.yml         # Mail platform
    platform-apps.yml         # Ops portal + changelog
  services/
    step-ca.yml
    openbao.yml
    windmill.yml
    ...                       # one file per service
  tasks/
    preflight.yml             # shared preflight assertions (imported by every play)
    post-verify.yml           # shared post-apply health verification
    notify.yml                # NATS + Mattermost notification on completion
```

### Environment-aware host resolution

All playbooks resolve their target host via the `env` variable rather than hardcoded hostnames:

```yaml
- hosts: "{{ hostvars | selectattr('environment', 'equalto', env | default('production')) | list }}"
```

The `platform.yml` computed facts (ADR 0063) provides per-environment IP addresses, subdomains, and service URLs so roles do not need `--limit` flags — setting `--extra-vars "env=staging"` is sufficient.

### Shared pre_tasks import

Every play imports a shared preflight task file at the start:

```yaml
pre_tasks:
  - import_tasks: tasks/preflight.yml
    vars:
      required_secrets: "{{ service_required_secrets | default([]) }}"
      required_hosts: "{{ service_required_hosts | default([]) }}"
```

`tasks/preflight.yml` performs:
1. assert all `required_secrets` are defined in `controller-local-secrets.json`
2. assert SSH connectivity to `required_hosts`
3. assert `env` is set to a known value (`production` or `staging`)
4. emit a start event to the mutation audit log (ADR 0066)

### Shared post-verify import

Every play imports a shared post-verification task file after the role runs:

```yaml
post_tasks:
  - import_tasks: tasks/post-verify.yml
    vars:
      service_health_probe_id: "{{ service_health_probe_id | default(omit) }}"
```

`tasks/post-verify.yml` calls the service's health probe from `health-probe-catalog.json` and fails the play if the probe does not return healthy, ensuring every live-apply self-verifies.

### Tagging strategy

All plays and tasks use a consistent three-tier tag hierarchy:

- `tier-1: infrastructure` — network, VMs, Proxmox host
- `tier-2: platform` — security, observability, data
- `tier-3: service` — individual named services

Example: `make live-apply playbook=site.yml tags=tier-2,observability` runs all observability services only.

### Dependency declaration

Playbooks that depend on another service being live declare it in a YAML front-matter comment block:

```yaml
# depends_on:
#   - step-ca.yml (step-ca must be provisioned for mTLS)
#   - openbao.yml (OpenBao must be unsealed for secrets)
```

The `make validate` gate parses these comments and emits a warning (not an error) if a dependency is not in a `live_applied` state in `workstreams.yaml`.

### `make` targets

```makefile
live-apply-group group=observability env=staging   # run playbooks/groups/observability.yml
live-apply-service service=grafana env=staging     # run playbooks/services/grafana.yml
live-apply-site env=production                     # run site.yml (full convergence)
```

## Consequences

- Running "all observability services" or "all security services" is a single command rather than a list of playbook files.
- Staging runs are first-class: `env=staging` is the only required change, not a combination of `--limit`, `--inventory`, and manual variable overrides.
- The shared preflight and post-verify tasks make every live-apply audited and self-verifying without per-playbook duplication.
- Restructuring the playbook directory is a breaking change for any scripts or CI workflows that reference specific playbook paths; these must be updated.

## Boundaries

- This ADR restructures the playbook layer only. Role internals are governed by ADR 0062. Variable resolution is governed by ADR 0063.
- The restructuring does not change what the playbooks do; it changes how they are organised and invoked. All existing roles remain unchanged.
- Multi-node (clustered) Proxmox topologies are out of scope; host resolution assumes single-node.
