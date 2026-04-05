# ADR 0358: Platform Health Contract and Inter-Service Dependency SLO

- Status: Accepted
- Implementation Status: Not Implemented
- Date: 2026-04-05
- Tags: health, slo, contracts, integration, observability, agent-coordination

## Context

The `build/platform-manifest.json` tracks runtime health for 80+ services.
However, health checks are defined inconsistently:

- Some services expose a `/health` HTTP endpoint.
- Some are checked by `docker inspect` container status.
- Some have no health check at all.
- The manifest records point-in-time health but does not declare what
  "healthy" means for a given service, or what health level is required
  before dependent services can safely start.

Without a formal health contract:

1. **Agents apply services on top of unhealthy dependencies.** An apply
   agent deploys Dify without checking that its required Postgres schema
   exists and is healthy.

2. **No SLO baseline.** There is no declared uptime target for each service,
   so alerts are either too noisy or absent.

3. **Integration health is invisible.** A service can be individually
   "healthy" (container running) but its integration with a dependency
   broken (wrong credentials, schema mismatch). No check tests the
   integration end-to-end.

4. **Recovery ordering is implicit.** When a VM reboots, services restart
   in undefined order. Without a dependency SLO contract, an operator
   cannot know whether Keycloak should be healthy before allowing n8n
   to start.

The integration contract registry (ADR 0353) declares *what* integrations
exist. This ADR declares *what health level* each integration requires and
*when* an agent or service may proceed.

## Decision

### 1. Health levels

Four health levels for any service:

| Level | Meaning | Container state |
|---|---|---|
| `dead` | Not running, no recovery in progress | Stopped or absent |
| `starting` | Starting up; not yet accepting requests | Running, health: starting |
| `degraded` | Running but one or more integrations are unhealthy | Running, health: unhealthy |
| `healthy` | Fully operational; all declared integrations passing | Running, health: healthy |

Services report one of these four levels. The platform manifest records the
current level. Only `healthy` means the service is safe for downstream
consumers to depend on.

### 2. Health contract in service.llm.yaml (ADR 0348 extension)

The `service.llm.yaml` file gains a `health_contract` block:

```yaml
health_contract:
  check_type: http          # http | docker | tcp | script
  endpoint: "http://localhost:8080/health/ready"
  expected_status: 200
  timeout_seconds: 5
  interval_seconds: 30

  # Minimum upstream health level required before this service starts
  requires_healthy:
    - service: postgres_ha
      min_level: healthy
    - service: openbao
      min_level: healthy
    - service: step_ca
      min_level: degraded    # certs can be pre-issued; degraded CA is acceptable

  # Integration probes: test the integration, not just the endpoint
  integration_probes:
    - name: postgres_connectivity
      command: "pg_isready -h {{ keycloak_postgres_host }} -p 5432 -U keycloak"
      on_failure: degraded
    - name: openbao_secret_readable
      command: >
        python3 scripts/openbao_probe.py read
        --path secret/keycloak/admin --expect-keys password
      on_failure: degraded

  slo:
    uptime_target_percent: 99.5
    max_restart_per_hour: 3
    alert_after_failures: 2
```

### 3. Health gate for agent applies

Before an agent applies a service, it must verify all `requires_healthy`
upstreams meet their `min_level`:

```yaml
# tasks/health_gate_check.yml
- name: Check upstream health gates for {{ target_service }}
  ansible.builtin.command: >
    python3 scripts/health_gate.py check
    --service {{ role_name }}
    --manifest build/platform-manifest.json
  register: health_gate
  failed_when: health_gate.rc == 1
  changed_when: false

- name: Fail if required upstreams are not at required health level
  ansible.builtin.fail:
    msg: "Health gate failed: {{ (health_gate.stdout | from_json).failures }}"
  when: (health_gate.stdout | from_json).failures | length > 0
```

`scripts/health_gate.py` reads `service.llm.yaml` for `requires_healthy`,
queries the platform manifest for current levels, and compares.

### 4. Integration probes

Integration probes run as part of the service verify task (`tasks/verify.yml`)
in each role. A failed integration probe downgrades the service to `degraded`
in the platform manifest — even if the service container itself is healthy.

The `common` role gains `run_integration_probes.yml`:

```yaml
- name: Run integration probes for {{ role_name }}
  ansible.builtin.command: "{{ item.command }}"
  loop: "{{ service_llm_config.health_contract.integration_probes }}"
  register: probe_results
  ignore_errors: true

- name: Update manifest health level based on probe results
  ansible.builtin.command: >
    python3 scripts/manifest_updater.py set-health
    --service {{ role_name }}
    --level {{ 'healthy' if probe_results.results | selectattr('failed') | list | length == 0 else 'degraded' }}
```

### 5. SLO monitoring

The SLO fields in `health_contract.slo` feed into the monitoring stack:

- `uptime_target_percent`: Grafana SLO panel and burn rate alert.
- `max_restart_per_hour`: Alert if Docker `RestartCount` delta exceeds threshold.
- `alert_after_failures`: ntfy alert after N consecutive health check failures.

The `monitoring_vm` role is updated to generate SLO alert rules from
aggregated `service.llm.yaml` `health_contract.slo` blocks.

### 6. Boot ordering for VM restart recovery

`playbooks/control-plane-recovery.yml` is updated to use the
`requires_healthy` graph from all `service.llm.yaml` files to generate
a topologically sorted start order:

1. `openbao`, `postgres_ha`, `step_ca` (no upstream deps).
2. `keycloak`, `gitea_runtime`, `minio` (depend only on tier 1).
3. `api_gateway_runtime`, `dify_runtime`, `n8n` (depend on tier 2).
4. Remaining services in dependency order.

`scripts/start_order.py` (new) generates this order from the dependency
graph and outputs an Ansible host group ordering.

### 7. Platform manifest update protocol

The platform manifest (`build/platform-manifest.json`) is the authoritative
runtime health record. Updates flow from:
- `manifest_updater.py set-health` called from verify tasks.
- Health probe results from Uptime Kuma (mapped to the four levels).
- `control_plane_recovery` role after VM restart.

The manifest must not be written by hand. All manifest updates go through
`scripts/manifest_updater.py` which enforces schema and emits a mutation
event (ADR 0354).

## Places That Need to Change

### `roles/*/service.llm.yaml`

Add `health_contract` block to all service files (added during the ADR 0348
migration effort).

### `scripts/health_gate.py` (new)

Layer 2 tool. Commands: `check --service`, `probe --service`, `status --all`.

### `scripts/start_order.py` (new)

Layer 1 tool. Commands: `generate --format ansible-groups`, `visualize --format mermaid`.

### `scripts/manifest_updater.py` (new or extended)

Adds `set-health --service --level` command. Validates against schema before
writing. Emits mutation event.

### `roles/common/tasks/health_gate_check.yml` (new)
### `roles/common/tasks/run_integration_probes.yml` (new)

Standard task files.

### `playbooks/control-plane-recovery.yml`

Use `start_order.py generate` output to drive start ordering.

### `roles/monitoring_vm/` (or `monitoring_stack`)

Generate SLO alert rules from `service.llm.yaml` aggregation.

### `docs/runbooks/platform-health-contract.md` (new)

Health level definitions, how to interpret degraded state, how to reset
health levels, SLO burn rate alert response.

## Consequences

### Positive

- Agents never deploy on top of unhealthy dependencies — eliminates a major
  class of "service starts broken" incidents.
- Integration probe results surface integration-layer failures that container
  health checks cannot detect (e.g., wrong DB password, revoked cert).
- Boot ordering is deterministic and documented — VM restart recovery is
  faster and less error-prone.
- SLO targets are declared in code alongside the service — not in a separate
  monitoring configuration that can drift.

### Negative / Trade-offs

- Health gate adds latency to every apply pre-flight: one manifest read
  plus N upstream health comparisons.
- Integration probes require the probed service to be accessible from the
  Ansible controller host. Internal services behind the VPN or gateway may
  need probe relay.
- SLO targets in `service.llm.yaml` are aspirational declarations. The
  monitoring stack enforces them only if the alert rule generation is
  run and the rules are deployed.
- Health level `degraded` is a spectrum — a service can be "degraded" because
  one optional integration is down, or because a critical database is
  unreachable. The four levels are a simplification.

## Related ADRs

- ADR 0071: Agent Observation Loop
- ADR 0085: IaC Boundary
- ADR 0165: Playbook and Role Metadata Standard
- ADR 0344: Single-Source Environment Topology
- ADR 0348: Per-Service LLM Context File (service.llm.yaml)
- ADR 0349: Agent Capability Manifest and Peer Discovery
- ADR 0353: Service Integration Contract Registry
- ADR 0354: Structured Agent Mutation Audit Log
- ADR 0355: Apply-Phase Serialization via Resource-Group Semaphore
