# ADR 0104: Service Dependency Graph and Failure Propagation Model

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.108.0
- Implemented In Platform Version: 0.130.20
- Implemented On: 2026-03-24
- Date: 2026-03-23

## Context

The platform runs 20+ services with complex interdependencies. When a service degrades or fails, operators must determine which other services are affected and in what order recovery should proceed. Currently, these dependencies exist only as implicit tribal knowledge:

- Operators know that "if OpenBao is down, nothing that needs secrets will work" — but there is no machine-readable record of which services depend on OpenBao
- The disaster recovery playbook (ADR 0100) defines a recovery order (Tier 0–5), but that order was derived from memory, not from a formal dependency model
- Drift detection (ADR 0091) and SLO burn rate alerts (ADR 0096) fire per-service but cannot answer "if Postgres is degraded, which SLOs are at risk?"
- The environment promotion gate (ADR 0073) cannot sequence deployments correctly without knowing that Keycloak depends on Postgres and that Windmill depends on Keycloak

Without a formal dependency graph, every operator must re-derive these relationships under pressure during incidents. And as the platform grows, the graph becomes impossible to keep accurate in human memory.

## Decision

We will define a **machine-readable service dependency graph** in `config/dependency-graph.json`, generate a visual dependency diagram for the docs site (ADR 0094), and integrate the graph into the ops portal (ADR 0093), the deployment sequencer, and the disaster recovery runbook (ADR 0100).

### Dependency model

Dependencies are classified by type and strength:

| Dependency type | Meaning | Example |
|---|---|---|
| `hard` | Service cannot start or function without the dependency | Keycloak → Postgres |
| `soft` | Service degrades gracefully if dependency is unavailable | Windmill → Mattermost (notifications only) |
| `startup_only` | Required at start time but not at runtime | step-ca → all services (certificate issuance) |
| `reads_from` | Reads data but does not block on availability | NetBox → Prometheus (optional metrics) |

### `config/dependency-graph.json`

```json
{
  "schema_version": "1.0",
  "nodes": [
    {
      "id": "postgres",
      "service": "postgres-lv3",
      "tier": 1,
      "vm": "postgres-lv3"
    },
    {
      "id": "step-ca",
      "service": "step-ca",
      "tier": 1,
      "vm": "docker-runtime-lv3"
    },
    {
      "id": "openbao",
      "service": "openbao",
      "tier": 1,
      "vm": "docker-runtime-lv3"
    },
    {
      "id": "keycloak",
      "service": "keycloak",
      "tier": 2,
      "vm": "docker-runtime-lv3"
    }
  ],
  "edges": [
    {
      "from": "keycloak",
      "to": "postgres",
      "type": "hard",
      "description": "Keycloak stores all user, session, and realm data in Postgres"
    },
    {
      "from": "keycloak",
      "to": "openbao",
      "type": "startup_only",
      "description": "Keycloak fetches its DB password from OpenBao at startup via secrets injection"
    },
    {
      "from": "windmill",
      "to": "keycloak",
      "type": "hard",
      "description": "Windmill uses Keycloak for OIDC authentication; workflows cannot authenticate without it"
    },
    {
      "from": "windmill",
      "to": "postgres",
      "type": "hard",
      "description": "Windmill stores workflow definitions, run history, and state in Postgres"
    },
    {
      "from": "netbox",
      "to": "postgres",
      "type": "hard",
      "description": "NetBox stores all IPAM and topology data in Postgres"
    },
    {
      "from": "mattermost",
      "to": "postgres",
      "type": "hard",
      "description": "Mattermost stores messages, channels, and users in Postgres"
    },
    {
      "from": "ops-portal",
      "to": "api-gateway",
      "type": "hard",
      "description": "The ops portal calls all platform actions through the API gateway"
    },
    {
      "from": "api-gateway",
      "to": "keycloak",
      "type": "hard",
      "description": "API gateway validates all JWTs against Keycloak JWKS endpoint"
    },
    {
      "from": "nats",
      "to": "openbao",
      "type": "startup_only",
      "description": "NATS fetches its credentials from OpenBao at startup"
    },
    {
      "from": "grafana",
      "to": "postgres",
      "type": "soft",
      "description": "Grafana uses Postgres for dashboard and alert state; degrades to read-only with local SQLite fallback"
    }
  ]
}
```

### Transitive impact analysis

`scripts/dependency_impact.py` provides transitive impact analysis:

```python
def compute_impact(failed_service: str, graph: DependencyGraph) -> ImpactReport:
    """Given a failed service, return all transitively affected services."""
    affected = set()
    queue = [failed_service]
    while queue:
        node = queue.pop()
        for edge in graph.edges_pointing_to(node):
            if edge.type == "hard" and edge.from_service not in affected:
                affected.add(edge.from_service)
                queue.append(edge.from_service)
    return ImpactReport(failed=failed_service, affected=sorted(affected))
```

Example output for `postgres` failure:

```
Impact of postgres failure:
  Hard dependencies (directly broken):
    - keycloak (cannot authenticate)
    - windmill (cannot run workflows)
    - netbox (IPAM queries fail)
    - mattermost (ChatOps unavailable)
  Transitive hard dependencies (broken via keycloak):
    - ops-portal (API gateway JWT validation fails without Keycloak)
    - api-gateway (JWT validation fails)
    - all OIDC-protected services (SSO broken)
  Soft dependencies (degraded):
    - grafana (dashboard state degraded; dashboards still render from cached data)
```

### Deployment sequencing

The promotion gate (ADR 0073) and the deployment runbook use the dependency graph to determine deployment order:

```python
def deployment_order(services_to_deploy: list[str], graph: DependencyGraph) -> list[str]:
    """Topological sort of services for safe sequential deployment."""
    return topological_sort(services_to_deploy, graph.edges)
```

If deploying Keycloak and Postgres in the same release, the graph ensures Postgres is deployed and healthy before Keycloak restart.

### Visual diagram

`scripts/generate_dependency_diagram.py` generates a Mermaid diagram from the graph JSON and includes it in the docs site:

```
graph TD
    postgres[(Postgres)]
    step-ca[step-ca]
    openbao[OpenBao]
    keycloak[Keycloak]
    windmill[Windmill]
    netbox[NetBox]
    mattermost[Mattermost]
    api-gateway[API Gateway]
    ops-portal[Ops Portal]

    keycloak -->|hard| postgres
    keycloak -->|startup_only| openbao
    windmill -->|hard| keycloak
    windmill -->|hard| postgres
    netbox -->|hard| postgres
    mattermost -->|hard| postgres
    api-gateway -->|hard| keycloak
    ops-portal -->|hard| api-gateway
```

### Ops portal integration

Each service card in the ops portal (ADR 0093) includes a **Impact** section showing:
- Services that depend on this service (would be affected if it fails)
- Services this service depends on (prerequisites for this service to function)

When a service's health probe fails, the ops portal displays the transitive impact list alongside the health status.

### Disaster recovery integration

The disaster recovery playbook (ADR 0100) recovery tiers are now derived from the dependency graph tier field rather than manually defined. Tier 1 nodes have no hard dependencies; Tier 2 nodes depend only on Tier 1; and so on. Any change to the graph automatically updates the recovery order.

## Consequences

**Positive**
- Incident response is faster: operators immediately know the blast radius of any failure without needing to reconstruct it from memory
- Deployment sequencing is correct by construction; no more "we deployed Keycloak before Postgres was ready"
- The recovery playbook tiers are derived from the graph, not hand-maintained; they stay correct as the platform evolves
- The visual diagram in the docs site is the authoritative architecture overview — better than any hand-drawn diagram because it is generated from the actual configuration

**Negative / Trade-offs**
- The dependency graph must be kept up-to-date as new services are added; the platform extension model (ADR 0107) will mandate this as part of the "new service checklist"
- The graph does not capture runtime behaviour that changes with configuration (e.g., Grafana's soft dependency on Postgres can be changed by configuring a different backend); the graph reflects the declared configuration, not all possible configurations
- Transitive impact analysis is worst-case; in practice, some services have retry/fallback behaviour that limits actual blast radius; the graph intentionally over-approximates to ensure operator caution

## Alternatives Considered

- **Derive dependencies from network traffic** (eBPF/service mesh): accurate but requires a service mesh agent on every VM; over-engineered for this scale; the declared dependency graph is more useful because it captures intended relationships, not just observed ones
- **Keep dependencies as comments in role README files**: non-machine-readable; cannot drive deployment ordering or impact analysis
- **Use NetBox relationships for dependency tracking**: NetBox (ADR 0054) can model device relationships but its data model is focused on physical/network topology, not service dependency semantics

## Related ADRs

- ADR 0033: Declarative service topology catalog (service nodes come from here)
- ADR 0073: Environment promotion gate (uses dependency order for deployment sequencing)
- ADR 0093: Interactive ops portal (impact analysis displayed per service)
- ADR 0094: Developer portal (visual diagram published here)
- ADR 0096: SLO definitions (SLO at-risk analysis uses the dependency graph)
- ADR 0100: Disaster recovery playbook (recovery tiers derived from the graph)
- ADR 0107: Platform extension model (new services must declare dependencies)

## Implementation Notes

- The canonical graph now lives in [config/dependency-graph.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/dependency-graph.json) and is schema-validated by [docs/schema/service-dependency-graph.schema.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/schema/service-dependency-graph.schema.json).
- [scripts/dependency_graph.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/dependency_graph.py) provides the shared parser, impact analysis, recovery-tier calculation, Mermaid rendering, and deployment-order logic used across the repo.
- Operators can inspect the graph through [scripts/dependency_impact.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/dependency_impact.py) and the `lv3 impact <service>` CLI surface in [scripts/lv3_cli.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/lv3_cli.py).
- The static ops portal generator now renders recovery tier and blast-radius context onto service cards via [scripts/generate_ops_portal.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_ops_portal.py).
- The current repo implementation exposes the intended `/v1/platform/dependency-graph` and `/v1/platform/dependency-graph/{service}/impact` routes through [scripts/platform_context_service.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/platform_context_service.py) so callers can adopt the API contract before ADR 0092's dedicated gateway runtime lands.
- Until ADR 0094's full docs-site generator is merged, the documentation-site integration is represented by the generated Markdown page [docs/site-generated/architecture/dependency-graph.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/site-generated/architecture/dependency-graph.md), produced by [scripts/generate_dependency_diagram.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_dependency_diagram.py) and validated as part of the repository checks.
