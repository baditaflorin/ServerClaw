# ADR 0353: Service Integration Contract Registry

- Status: Accepted
- Implementation Status: Not Implemented
- Date: 2026-04-05
- Tags: integration, contracts, infrastructure, dry, service-catalog, validation

## Context

The platform hosts 80+ services that integrate with each other through:
- Shared PostgreSQL databases (e.g., Keycloak, Gitea, Dify, Directus each use
  a distinct Postgres database on the same HA cluster).
- OIDC/SSO integration (most services delegate auth to Keycloak via api-gateway).
- Object storage (many services write to MinIO buckets).
- Secret retrieval (all services read from OpenBao at startup or via consul-template).
- Message bus (NATS JetStream for internal events and agent coordination).
- Observability (Loki log shipping, Telegraf metrics, Grafana dashboards).

These integrations are implicit: they exist because roles pass the right
hostnames and credentials to the right env vars. There is no single place
that declares "service A integrates with service B via protocol P".

Consequences of this gap:
1. **No integration validation.** An agent can deploy service A without
   knowing that service B (which A depends on) is degraded.
2. **No impact analysis.** Restarting service B requires knowing all services
   that will be affected. Today this requires reading every role's `defaults/`.
3. **No dead integration detection.** A removed service may leave stale
   integration entries in other services' configs.
4. **High token cost.** LLM agents must load multiple role `defaults/` to
   reconstruct integration topology, paying thousands of tokens.

ADR 0348 (`service.llm.yaml`) establishes `depends_on` and `consumed_by` lists
per service. This ADR formalises the **integration contract** between any two
services: what protocol, what data flows, what failure modes are acceptable,
and what health check validates the integration.

## Decision

### 1. Integration contract file

A new file type `integration.yaml` is placed in
`config/integrations/<consumer>--<provider>.yaml`.

```yaml
# config/integrations/keycloak--postgres_ha.yaml
schema_version: 1
consumer: keycloak_runtime
provider: postgres_ha
protocol: postgres        # postgres | oidc | s3 | nats | http | tls | smtp
direction: consumer→provider

connection:
  host_var: "keycloak_postgres_host"    # variable name in consumer defaults
  port: 5432
  database: keycloak
  auth: openbao                         # openbao | static | env | none

health_check:
  command: "pg_isready -h {{ keycloak_postgres_host }} -p 5432 -U keycloak"
  timeout_seconds: 5
  on_failure: "block_consumer_start"   # block_consumer_start | alert_only | ignore

failure_mode: hard        # hard (consumer cannot function) | soft (degraded) | optional

adr_authority: "0022"    # ADR that first established this integration
last_verified: "2026-04-05"
```

### 2. Protocol enum

| Protocol | Covers |
|---|---|
| `postgres` | TCP connection to PostgreSQL |
| `oidc` | OIDC discovery + token validation |
| `s3` | S3-compatible object storage (MinIO) |
| `nats` | NATS JetStream subject publish/subscribe |
| `http` | REST API or webhook over HTTP/HTTPS |
| `tls` | TLS certificate issuance (step-ca) |
| `smtp` | SMTP mail delivery |
| `loki` | Log shipping to Loki |
| `metrics` | Telegraf → InfluxDB metrics pipeline |

### 3. Integration registry index

`config/integrations/.index.yaml` (generated):

```yaml
generated: "2026-04-05"
total_integrations: 127
by_consumer:
  keycloak_runtime: [postgres_ha, step_ca, openbao]
  dify_runtime: [postgres_ha, redis, minio, openbao, step_ca, nats_jetstream]
  ...
by_provider:
  postgres_ha: [keycloak_runtime, gitea_runtime, dify_runtime, ...]
  openbao: [all]   # shorthand for universal secret provider
by_protocol:
  postgres: 23
  oidc: 41
  s3: 12
  ...
```

`scripts/generate_integration_index.py` generates the index from all
`config/integrations/*.yaml` files.

### 4. Integration validation in pre-flight

`playbooks/tasks/preflight.yml` includes an integration health check step:

```yaml
- name: Validate upstream integrations for {{ target_service }}
  ansible.builtin.command: >
    python3 scripts/integration_check.py validate
    --consumer {{ role_name }}
    --fail-on hard
  register: integration_check
  failed_when: integration_check.rc == 1
  changed_when: false
```

`scripts/integration_check.py` (new):

```
integration_check.py validate --consumer <role>   # check all hard dependencies
integration_check.py impact --provider <role>     # list all consumers that depend on <role>
integration_check.py orphans                       # integrations with no live role files
integration_check.py graph --format mermaid        # output dependency graph
```

### 5. Mandatory integration declaration

An integration between two services that passes secrets, connection strings, or
auth tokens **must** have a corresponding `integration.yaml` file. This is
enforced by:

1. A `tests/test_integration_registry.py` test that loads all role `defaults/`
   and checks whether any `_host`, `_url`, or `_dsn` variable that points to
   another known service has a matching integration file.
2. Pre-commit hook: if a role `defaults/main.yml` is modified and introduces
   a new cross-service reference, the hook warns if no matching integration
   file exists.

### 6. Impact analysis for agents

Before an agent restarts or redeploys a service (`provider`), it must call:

```
integration_check.py impact --provider <role_name>
```

The output lists all `hard` consumers — services that will fail if the provider
is unavailable. The agent must either:
- Schedule the restart during a maintenance window and notify operators.
- Verify all hard consumers are currently healthy (can tolerate a brief outage).
- Or explicitly acknowledge the impact in its workstream note.

This check is added to the capability manifest preflight (ADR 0349).

## Places That Need to Change

### `config/integrations/` (new directory)

Populate with `<consumer>--<provider>.yaml` files for all known integrations.
Initial target: all `postgres`, `oidc`, and `s3` integrations (~60 files).

### `scripts/generate_integration_index.py` (new)

Generates `config/integrations/.index.yaml` from individual files.

### `scripts/integration_check.py` (new)

Layer 2 tool per ADR 0345. Commands: `validate`, `impact`, `orphans`, `graph`.

### `playbooks/tasks/preflight.yml`

Add `integration_check.py validate` step.

### `tests/test_integration_registry.py` (new)

Validates completeness: no undeclared cross-service variable references.

### `.pre-commit-config.yaml`

Add integration-registry completeness hook.

### `scripts/generate_service_catalog.py`

Augment generated catalog with integration index data.

### `docs/runbooks/integration-registry.md` (new)

How to add an integration, run impact analysis, interpret graph output.

## Consequences

### Positive

- Complete, machine-readable map of all service integrations — no longer
  reconstructed by reading dozens of `defaults/` files.
- Pre-flight validates upstreams before applying a service — fewer
  "service deployed but broken at startup" incidents.
- Impact analysis makes maintenance window planning deterministic.
- `integration_check.py graph` outputs a Mermaid diagram usable in runbooks.

### Negative / Trade-offs

- Initial file creation for 60–127 integrations is significant authoring work.
- The `test_integration_registry.py` completeness check may generate false
  positives for variables that reference external services (Hetzner DNS, etc.)
  — blocklist needed.
- Integration files can go stale if a service changes its protocol or moves
  hosts; no auto-sync from `defaults/`.

## Related ADRs

- ADR 0085: IaC Boundary
- ADR 0165: Playbook and Role Metadata Standard
- ADR 0327: Sectional Agent Discovery Registries
- ADR 0344: Single-Source Environment Topology
- ADR 0348: Per-Service LLM Context File (service.llm.yaml)
- ADR 0349: Agent Capability Manifest and Peer Discovery
- ADR 0352: Token-Budgeted Agent Onboarding Packs
