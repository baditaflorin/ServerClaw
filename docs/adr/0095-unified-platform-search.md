# ADR 0095: Unified Search Across Platform Services

- Status: Superseded
- Implementation Status: Superseded by ADR 0121
- Implemented In Repo Version: 0.119.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-23

## Context

The platform stores information about its own state across at least eight different locations:

| Source | What it contains |
|---|---|
| NetBox | VM topology, IP addresses, IPAM records |
| Grafana/Loki | Service logs (last 30 days) |
| Mutation audit log | Record of every change made through the platform |
| `config/service-capability-catalog.json` | Service definitions and capabilities |
| `config/subdomain-catalog.json` | Published subdomains |
| ADRs (`docs/adr/`) | Architecture decisions and implementation details |
| Windmill workflow history | Past workflow runs and their outputs |
| Mattermost | Operator and agent chat history, incident discussions |

When investigating an incident or planning a change, an operator must query each of these independently. "What do we know about `postgres-lv3`?" requires: checking NetBox for the IP, Loki for recent logs, the audit log for recent changes, the service catalog for what runs on it, and Mattermost for any recent conversation. This information is not correlated anywhere.

Agents (ADR 0046, 0069) face the same problem: an agent answering "what happened to the mail platform last week?" must call multiple tools and synthesise their outputs. This increases agent latency and the chance of incomplete answers.

The platform has Open WebUI (ADR 0060) as an AI workbench and a RAG context layer (ADR 0070) for platform queries. The RAG context provides document retrieval but is limited to pre-indexed documents. A complementary keyword-and-structured search layer is needed for operational queries.

## Decision

We will deploy **Zinc Search** (a lightweight Elasticsearch-compatible search engine) on `docker-runtime-lv3` and build a search indexer that ingests the six primary platform data sources on a schedule. A search endpoint is exposed through the platform API gateway (ADR 0092) at `/v1/platform/search` and integrated into the ops portal (ADR 0093) and the `lv3 search` CLI command.

### Why Zinc Search

Zinc Search is chosen over Elasticsearch/OpenSearch because:
- Single binary, ~50 MB RAM idle footprint; appropriate for a single-node homelab
- Elasticsearch-compatible query API; indexing scripts are portable if we later migrate
- No external dependencies (no separate JVM, no ZooKeeper)
- Provides a built-in minimal search UI at port 4080 for operator exploration

### Indexed sources and schedules

| Source | Index name | Indexer script | Schedule |
|---|---|---|---|
| Service capability catalog | `platform-services` | `scripts/search_index_catalog.py` | On every `main` merge |
| Subdomain catalog | `platform-subdomains` | `scripts/search_index_catalog.py` | On every `main` merge |
| ADRs | `platform-adrs` | `scripts/search_index_adrs.py` | On every `main` merge |
| Mutation audit log | `platform-audit` | `scripts/search_index_audit.py` | Every 15 minutes |
| NetBox (VMs + IPs) | `platform-topology` | `scripts/search_index_netbox.py` | Every hour |
| Windmill workflow runs | `platform-workflows` | `scripts/search_index_windmill.py` | Every 15 minutes |

Loki logs are explicitly **not** indexed in Zinc — Loki already provides a query API (`/loki/api/v1/query_range`) with label-based filtering. Duplicating logs into a second store would double storage for marginal benefit. The search endpoint instead issues a passthrough Loki query for log searches.

### Document schema

All indexed documents share a common envelope:

```json
{
  "id": "audit:2026-03-23T10:15:00Z:openbao-rotate",
  "source": "audit",
  "timestamp": "2026-03-23T10:15:00Z",
  "title": "Secret rotated: openbao/platform-db-password",
  "body": "Operator ops@lv3.org rotated secret openbao/platform-db-password. Affected services: netbox, windmill.",
  "tags": ["openbao", "secret-rotation", "netbox", "windmill"],
  "url": "/v1/platform/audit/2026-03-23T10:15:00Z:openbao-rotate",
  "related_service": "openbao",
  "related_vm": "docker-runtime-lv3"
}
```

The consistent `source`, `tags`, `related_service`, and `related_vm` fields enable faceted filtering on top of full-text search.

### Search API endpoint

The platform gateway exposes `/v1/platform/search`:

```http
GET /v1/platform/search?q=postgres&sources=audit,topology&limit=20
Authorization: Bearer <keycloak-token>
```

Response:

```json
{
  "query": "postgres",
  "total": 47,
  "results": [
    {
      "source": "topology",
      "title": "postgres-lv3 (VMID 150)",
      "body": "PostgreSQL VM at 10.10.10.50. Disk: 80GB. RAM: 4096MB.",
      "timestamp": "2026-03-23T08:00:00Z",
      "tags": ["postgres", "vm", "production"],
      "url": "/v1/platform/topology/vms/150"
    },
    {
      "source": "audit",
      "title": "Postgres password rotated",
      "body": "...",
      "timestamp": "2026-03-22T14:30:00Z"
    }
  ]
}
```

### Ops portal integration

The ops portal (ADR 0093) includes a search bar in the header (`Cmd+K` shortcut). Search results are grouped by source with icons, rendered with HTMX `hx-get` on each keystroke (debounced 300ms). Clicking a result deep-links to the relevant resource: audit log entry, NetBox VM page, ADR on the docs site (ADR 0094), or Windmill workflow run.

### `lv3 search` command

```bash
lv3 search "postgres password"
# →  [audit] 2026-03-22  Postgres password rotated (ops@lv3.org)
#    [adr]   ADR 0026     Dedicated PostgreSQL VM baseline
#    [topo]  postgres-lv3  10.10.10.50, VMID 150
```

### Agent tool

The agent tool registry (ADR 0069) registers `platform_search` as a tool:

```json
{
  "tool_id": "platform_search",
  "description": "Search across platform services, audit log, topology, ADRs, and workflow history",
  "endpoint": "/v1/platform/search",
  "parameters": {
    "q": {"type": "string", "required": true},
    "sources": {"type": "array", "items": {"type": "string"}},
    "limit": {"type": "integer", "default": 10}
  }
}
```

This replaces the pattern of agents calling five separate tools to answer a cross-source question.

## Consequences

**Positive**
- Incident investigation time reduced: a single query surfaces topology, recent changes, and related discussions in one result set
- Agent platform queries become faster and more complete; fewer multi-tool round trips
- ADRs become searchable in operational context ("which ADR covers certificate rotation?") without navigating the docs site
- `platform-audit` index enables compliance queries: "show all secret rotations in the last 30 days"

**Negative / Trade-offs**
- Zinc Search is a new service with a persistent data volume; it must be included in backup scope (ADR 0020) and monitored
- Re-indexing on every merge adds ~5 seconds to the Windmill post-merge workflow; this is acceptable
- Search results are only as fresh as the indexer schedule; the mutation audit log is at most 15 minutes stale, which is acceptable for operational queries (not for incident real-time feeds, which use NATS)

## Alternatives Considered

- **Elasticsearch / OpenSearch**: same feature set but 4–8× the resource footprint; a dedicated VM would be required, which is out of proportion for a homelab
- **SQLite FTS5**: zero-dependency full-text search; lacks the REST API, faceted filtering, and multi-source federation needed; would require building the entire search facade from scratch
- **Meilisearch**: excellent typo-tolerance and relevance tuning; does not support structured aggregation queries as well as Zinc; Zinc's Elasticsearch API compatibility is more valuable for the existing Loki/Grafana tooling

## Related ADRs

- ADR 0033: Declarative service topology catalog (indexed as `platform-services`)
- ADR 0054: NetBox for topology and IPAM (source for `platform-topology` index)
- ADR 0060: Open WebUI (search complements RAG; different use cases)
- ADR 0066: Mutation audit log (source for `platform-audit` index)
- ADR 0069: Agent tool registry (`platform_search` tool registration)
- ADR 0070: RAG context for platform queries (complementary: RAG for document Q&A; search for structured operational queries)
- ADR 0092: Unified platform API gateway (`/v1/platform/search` endpoint)
- ADR 0093: Interactive ops portal (search bar integration)
