# ADR 0348: Per-Service LLM Context File (service.llm.yaml)

- Status: Accepted
- Implementation Status: Not Implemented
- Date: 2026-04-05
- Tags: llm, agent-discovery, token-budget, documentation, service-catalog, dry

## Context

LLM agents operating on this platform repeatedly need to answer questions like:

- What does this service do?
- What are its upstream and downstream dependencies?
- What secrets does it consume?
- What is its health-check endpoint?
- What Ansible role and playbook deploy it?
- What ADRs govern its architecture?

Today agents get this context from three sources:
1. `build/onboarding/service-catalog.yaml` (60 KB — the full catalog).
2. The role's `README.md` (prose, high token cost, inconsistently formatted).
3. The role's `meta/argument_specs.yml` (machine-readable but not LLM-oriented).

Loading the full 60 KB service catalog to answer a question about one service
consumes ~15,000 tokens per agent invocation. With tens of agents running
concurrently each needing service context, this is unsustainable.

The `build/onboarding/` generated packs (ADR 0327) exist but are task-scoped,
not service-scoped. The onboarding packs load 19–43 KB of general context
regardless of the specific service being operated on.

## Decision

Each Ansible role that deploys a service ships a `service.llm.yaml` file
co-located with the role at `roles/<role_name>/service.llm.yaml`.

### Schema

```yaml
# roles/keycloak_runtime/service.llm.yaml
schema_version: 1
service: keycloak
role: keycloak_runtime
description: >
  Identity provider (OIDC/SAML). Issues tokens for all platform SSO.
  Backed by keycloak_postgres. Exposed via api-gateway at /auth.
kind: auth          # auth | data | observability | automation | ai | infra | communication
vmid: 104           # primary VM (or null for multi-vm)
port: 8080
health_check: "http://localhost:8080/health/ready"
playbook: "playbooks/keycloak.yml"
service_playbook: "playbooks/services/keycloak.yml"   # null if none

depends_on:
  - service: postgres_ha
    reason: primary database
  - service: step_ca
    reason: TLS cert issuance
  - service: openbao
    reason: secret retrieval at runtime

consumed_by:
  - service: api_gateway_runtime
    reason: OIDC reverse-proxy auth
  - service: grafana_sso
    reason: SSO login
  - service: dify_runtime
    reason: user authentication

secrets:
  - name: keycloak_admin_password
    store: openbao
    path: "secret/keycloak/admin"
  - name: keycloak_db_password
    store: openbao
    path: "secret/keycloak/db"

adrs:
  - number: "0022"
    summary: Keycloak as platform IdP
  - number: "0178"
    summary: Keycloak postgres HA failover

operator_notes: >
  After config changes always run the service playbook, not the full playbook.
  Restart order: postgres → keycloak → api-gateway reload.
  Break-glass: local admin account at /auth/admin, credentials in openbao.

token_budget: 300   # approximate tokens this file costs when loaded
```

### Required fields

| Field | Type | Required |
|---|---|---|
| `schema_version` | int | yes |
| `service` | string | yes |
| `role` | string | yes |
| `description` | string (≤400 chars) | yes |
| `kind` | enum | yes |
| `playbook` | path | yes |
| `depends_on` | list | yes (may be empty) |
| `consumed_by` | list | yes (may be empty) |
| `secrets` | list | yes (may be empty) |
| `adrs` | list | yes (may be empty) |
| `token_budget` | int | yes |

### Token budget constraint

`description` must not exceed 400 characters. `operator_notes` must not exceed
600 characters. The whole file must render to ≤500 tokens. These limits are
enforced by `tests/test_service_llm_yaml.py`.

### Agent loading protocol

Agents must NOT load `build/onboarding/service-catalog.yaml` for single-service
queries. Instead:

1. Identify the role name from the workstream or task context.
2. Load only `roles/<role>/service.llm.yaml` (≤500 tokens).
3. For dependency traversal, load dependency role files on demand (lazy).

```python
# Canonical pattern for agent context loading
def load_service_context(role_name: str, depth: int = 0) -> dict:
    path = Path(f"collections/ansible_collections/lv3/platform/roles/{role_name}/service.llm.yaml")
    ctx = yaml.safe_load(path.read_text())
    if depth > 0:
        ctx["_deps"] = [
            load_service_context(dep["service"], depth - 1)
            for dep in ctx.get("depends_on", [])
        ]
    return ctx
```

Maximum lazy depth recommended: 1 (direct dependencies only). Full graph
traversal is reserved for the `build/onboarding/service-catalog.yaml`
generation script.

### Catalog generation

`scripts/generate_service_catalog.py` is updated to aggregate `service.llm.yaml`
files from all roles rather than maintaining the catalog by hand. The catalog
becomes a derived output; the per-role file is the source of truth.

### Scaffold

The `roles/_template/service_scaffold/service.llm.yaml.tpl` template is added
so that `make scaffold-role NAME=<foo>` generates the stub automatically.

## Places That Need to Change

### `roles/_template/service_scaffold/`

Add `service.llm.yaml.tpl` with all required fields as comments/stubs.

### `scripts/generate_service_catalog.py` (updated)

Read `service.llm.yaml` from each role instead of a hand-maintained input.
Output `build/onboarding/service-catalog.yaml` unchanged in schema.

### `tests/test_service_llm_yaml.py` (new)

- Validate schema_version, required fields, description length, token_budget field.
- Assert `token_budget` ≤ 500 for every file.
- Verify all `depends_on[].service` values reference an existing role.

### `docs/runbooks/agent-service-context-loading.md` (new)

Document the loading protocol and anti-patterns (e.g., loading the full
catalog for a single-service task).

### `build/onboarding/service-catalog.yaml`

Regenerated from per-role `service.llm.yaml` files. No longer hand-edited.

## Consequences

### Positive

- Single-service agent context drops from ~15,000 tokens to ≤500 tokens.
- Source of truth for integration dependencies moves into the role directory —
  co-located with the code it describes, updated with the same PR.
- Catalog generation becomes deterministic and testable.
- `consumed_by` makes reverse dependency traversal explicit and machine-readable.

### Negative / Trade-offs

- All 153 existing roles need a `service.llm.yaml` file — large one-time
  authoring effort. Roles without the file must be blocklisted from agent tasks
  until added (not fail-open).
- `token_budget` field is an estimate; actual tokenization depends on the
  model's tokenizer. The 500-token limit is conservative for tiktoken-compatible
  counts and may be recalibrated.
- Keeping `service.llm.yaml` in sync with `argument_specs.yml` and `README.md`
  requires discipline — a `make check-llm-sync` target should lint for obvious
  drift.

## Related ADRs

- ADR 0165: Playbook and Role Metadata Standard
- ADR 0327: Sectional Agent Discovery Registries and Generated Onboarding Packs
- ADR 0334: Example-First Inventory and Service Identity Catalogs
- ADR 0335: Public-Safe Agent Onboarding Entrypoints
- ADR 0343: Operator Tool Interface Contract
