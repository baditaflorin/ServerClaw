# ADR 0117: Service Dependency Graph As First-Class Runtime

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.117.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

ADR 0104 proposed capturing a service dependency graph to support capacity planning and change impact analysis. The dependency graph was proposed as a static document. The platform has evolved significantly since then, and the dependency graph now needs to be more than a static snapshot — it needs to be a runtime resource that automation, triage, and risk-scoring can traverse in real time.

The gaps today are concrete:

- **Blast-radius analysis is manual**: when an operator plans a deployment or maintenance action, they must mentally enumerate which services depend on the target. This is error-prone and increasingly complex as the platform grows.
- **Incident correlation is unassisted**: the triage engine (ADR 0114) currently knows about service health per service but cannot automatically determine whether a failing service is the root cause or a downstream victim of a different failure.
- **Risk scoring is approximate**: the risk scorer (ADR 0116) needs a `downstream_count` signal. Today this is a static config value rather than a live graph traversal.
- **Health propagation is absent**: if the platform Postgres instance (VM 150) becomes degraded, all services that depend on it should show a derived `degraded` status, even if their own health probes are still passing. Today, each service's health is assessed independently.

## Decision

We will persist a machine-usable dependency graph for services, hosts, networks, DNS names, certificates, and data flows as a directed acyclic graph (DAG) stored in Postgres, queryable via a graph traversal API, and refreshed automatically from NetBox, the workflow catalog, and the world-state materializer.

### Graph model

Nodes and edges are stored in two tables in the `graph` Postgres schema:

```sql
CREATE TABLE graph.nodes (
    id          TEXT PRIMARY KEY,           -- e.g. 'service:netbox', 'host:docker-runtime-lv3'
    kind        TEXT NOT NULL,              -- service | host | network | dns | cert | secret | vm
    label       TEXT NOT NULL,
    tier        INTEGER,                    -- criticality tier from ADR 0075
    metadata    JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE graph.edges (
    id          BIGSERIAL PRIMARY KEY,
    from_node   TEXT NOT NULL REFERENCES graph.nodes(id),
    to_node     TEXT NOT NULL REFERENCES graph.nodes(id),
    edge_kind   TEXT NOT NULL,              -- depends_on | hosted_on | resolved_by | secured_by | replicates_to
    metadata    JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX graph_edges_from_idx ON graph.edges (from_node);
CREATE INDEX graph_edges_to_idx   ON graph.edges (to_node);
```

### Edge kinds

| Edge kind | Meaning | Example |
|---|---|---|
| `depends_on` | Service A requires Service B to function | `service:netbox → service:postgres` |
| `hosted_on` | Service A runs on Host B | `service:netbox → host:docker-runtime-lv3` |
| `resolved_by` | Service A's DNS name is authoritative on DNS server B | `service:netbox → dns:internal-resolver` |
| `secured_by` | Service A's TLS certificate is issued by CA B | `service:netbox → cert:step-ca-internal` |
| `replicates_to` | Node A replicates data to Node B | `host:postgres-primary → host:postgres-replica` |

### Graph population

The graph is initially populated and continuously refreshed from three sources:

1. **NetBox** (via world-state materializer, ADR 0113): device-to-rack relationships, IP assignments, VLAN membership, and DNS entries are imported as `hosted_on`, `resolved_by`, and network edges.

2. **Workflow catalog** (ADR 0048): the `depends_on` field in `config/workflow-catalog.json` declarations is imported as `depends_on` edges between services.

3. **Explicit graph manifest**: a version-controlled file `config/dependency-graph.yaml` allows operators to declare edges that cannot be inferred from NetBox or the workflow catalog (e.g., application-level dependencies between services that share a Postgres database).

### Traversal API

The graph traversal module exposes the operations required by the triage engine, risk scorer, and health propagation:

```python
# platform/graph/client.py

graph = DependencyGraphClient()

# Downstream blast radius of a node
downstream = graph.descendants("service:postgres")
# Returns: [service:keycloak, service:netbox, service:windmill, service:mattermost, ...]

# Upstream dependency chain of a node
upstream = graph.ancestors("service:netbox")
# Returns: [service:postgres, host:docker-runtime-lv3, cert:step-ca-internal, ...]

# Shortest dependency path between two nodes
path = graph.path("service:netbox", "host:proxmox-host-lv3")

# All nodes within N hops of a node
neighbourhood = graph.neighbourhood("service:postgres", radius=2)

# Propagated health: if postgres is degraded, what services are affected?
affected = graph.health_propagation("service:postgres", status="degraded")
# Returns: [{"node": "service:keycloak", "derived_status": "degraded", "path": [...]}]
```

### Health propagation

Health propagation runs as a Windmill workflow triggered on every `platform.world_state.refreshed` event for the `service_health` surface. For each service that transitioned to `degraded` or `down`, the propagation workflow:

1. Traverses `ancestors` in reverse (find everything that depends on the degraded service).
2. For each downstream service whose own health probe is still passing, emits a `derived_health_degraded` event to NATS.
3. Writes a propagation record to the ledger (ADR 0115).

The triage engine (ADR 0114) consumes `derived_health_degraded` events and uses them as high-confidence evidence in its root-cause hypothesis ranking.

### Platform API gateway endpoint

The dependency graph is exposed via the platform API gateway (ADR 0092):

```
GET /v1/graph/nodes                     # list all nodes
GET /v1/graph/nodes/{id}/descendants    # blast radius
GET /v1/graph/nodes/{id}/ancestors      # dependency chain
GET /v1/graph/nodes/{id}/health         # propagated health status
GET /v1/graph/path?from={a}&to={b}      # shortest path
```

## Consequences

**Positive**

- Blast-radius analysis is a single API call. The risk scorer, triage engine, and ops portal all consume the same graph rather than maintaining their own dependency data.
- Health propagation makes it possible to distinguish root cause from victim in multi-service incidents without any LLM reasoning.
- The dependency graph manifest (`config/dependency-graph.yaml`) is version-controlled; dependency changes are auditable and reviewable like any other config change.
- Graph traversal is CPU-cheap: recursive CTEs or adjacency-list BFS over a Postgres table with ~100 nodes and ~500 edges completes in milliseconds.

**Negative / Trade-offs**

- Graph quality depends on disciplined metadata. Missing `depends_on` declarations mean blast-radius analysis will under-count affected services. Initial population will be incomplete.
- The graph must be kept in sync with the live platform; stale edges (for decommissioned services) degrade triage precision.
- Applications with undeclared database dependencies (services that share a DB without a declared `depends_on` edge) will produce incorrect health propagation results until their edges are added.

## Boundaries

- The dependency graph covers runtime operational dependencies (who needs whom to function). It does not model build-time or code-level dependencies; those are out of scope.
- The graph is a derived artifact, not the source of truth. NetBox is still the authority for network topology; the workflow catalog is still the authority for automation composition.

## Related ADRs

- ADR 0048: Command catalog (workflow-level dependency declarations)
- ADR 0054: NetBox topology (host and network node source)
- ADR 0058: NATS event bus (health propagation event delivery)
- ADR 0075: Service capability catalog (node criticality tiers)
- ADR 0092: Unified platform API gateway (graph query endpoints)
- ADR 0104: Service dependency graph (original proposal, superseded by this ADR)
- ADR 0113: World-state materializer (graph refresh trigger)
- ADR 0114: Rule-based incident triage engine (consumes blast-radius and health propagation)
- ADR 0115: Event-sourced mutation ledger (propagation records written here)
- ADR 0116: Change risk scoring (consumes downstream_count from graph traversal)
