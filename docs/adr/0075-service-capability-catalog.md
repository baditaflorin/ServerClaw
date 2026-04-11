# ADR 0075: Service Capability Catalog

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.69.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

Platform knowledge about running services is fragmented across multiple files:

- `versions/stack.yaml` — VM topology and identities
- `config/uptime-kuma/monitors.json` — health check URLs
- `config/health-probe-catalog.json` (ADR 0064) — liveness/readiness probes
- `config/image-catalog.json` (ADR 0068) — container images
- `config/secret-catalog.json` (ADR 0065) — secrets per service
- `docs/runbooks/*.md` — operational procedures
- `docs/adr/*.md` — design decisions

No single file answers: "for this service, what is its URL, what VM does it run on, what is its runbook, what is its health probe, what images does it use, and how does an operator or agent reach it?"

Agents querying platform context (ADR 0070) must assemble this from multiple sources and risk returning stale or incomplete answers. The operations portal (ADR 0074) needs a single structured input.

What is missing is a **service capability catalog** — a machine-readable, schema-validated index of every service the platform runs, with all operationally relevant fields in one place.

## Decision

We will define a canonical `config/service-capability-catalog.json` that is the authoritative index for every service on the platform.

### Schema

```json
{
  "$schema": "docs/schema/service-capability-catalog.schema.json",
  "services": [
    {
      "id": "grafana",
      "name": "Grafana",
      "description": "Metrics dashboards and alerting",
      "category": "observability",
      "vm": "monitoring",
      "vmid": 140,
      "internal_url": "http://10.10.10.40:3000",
      "public_url": "https://grafana.example.com",
      "subdomain": "grafana.example.com",
      "exposure": "edge-published",
      "health_probe_id": "grafana",
      "image_catalog_ids": ["grafana"],
      "secret_catalog_ids": ["grafana-admin"],
      "adr": "0011",
      "runbook": "docs/runbooks/monitoring-stack.md",
      "grafana_dashboard_uid": "platform-observability",
      "tags": ["monitoring", "metrics", "dashboards"],
      "environments": {
        "production": { "url": "https://grafana.example.com" },
        "staging": { "url": "https://grafana.staging.example.com" }
      }
    }
  ]
}
```

### Field definitions

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Stable machine identifier (snake_case) |
| `name` | string | yes | Human-readable display name |
| `description` | string | yes | One-line purpose statement |
| `category` | enum | yes | `observability`, `security`, `automation`, `data`, `communication`, `access`, `infrastructure` |
| `vm` | string | yes | Hosting VM hostname |
| `vmid` | integer | yes | Proxmox VMID |
| `internal_url` | string | yes | Internal HTTP/HTTPS URL |
| `public_url` | string | no | Public edge URL if applicable |
| `subdomain` | string | no | Canonical subdomain |
| `exposure` | enum | yes | `edge-published`, `private-only`, `informational-only` |
| `health_probe_id` | string | no | Reference to health-probe-catalog.json entry |
| `image_catalog_ids` | array | no | References to image-catalog.json entries |
| `secret_catalog_ids` | array | no | References to secret-catalog.json entries |
| `adr` | string | no | Governing ADR number |
| `runbook` | string | no | Path to primary operational runbook |
| `tags` | array | no | Searchable tags |
| `environments` | object | no | Per-environment URL overrides |

### Maintenance model

The service catalog is the source of truth for the portal generator, the RAG corpus (ADR 0070), and agent context queries. It must be updated when:

- a new service is added (as part of its onboarding scaffold, ADR 0078)
- a service's URL, subdomain, or exposure changes
- a service is retired (entry removed or `status: deprecated` added)

The `make validate` gate includes a schema validation step for `config/service-capability-catalog.json` against `docs/schema/service-capability-catalog.schema.json`.

### Cross-reference validation

A validation script (`scripts/validate_service_catalog.py`) checks that:
- the catalog matches `docs/schema/service-capability-catalog.schema.json`
- every referenced health probe exists in `config/health-probe-catalog.json`
- every referenced image exists in `config/image-catalog.json`
- every referenced secret exists in `config/secret-catalog.json`
- every referenced Uptime Kuma monitor exists in `config/uptime-kuma/monitors.json`
- every `runbook` path exists in `docs/runbooks/`
- active services stay aligned with the canonical service topology and observed guest inventory
- the catalog covers exactly the services declared in `config/health-probe-catalog.json`

This script runs as part of `make validate`.

## Consequences

- The operations portal (ADR 0074) and the RAG index (ADR 0070) have a single, validated source of truth instead of assembling answers from multiple files.
- Adding a new service now has a defined checklist: ADR, role, playbook, health probe entry, image catalog entry, secret catalog entry, and service catalog entry.
- The cross-reference validation script surfaces broken links before they reach main.
- The catalog will diverge from reality if service operators update their configs without updating the catalog. The observation loop (ADR 0071) can detect URL changes and flag them.

## Boundaries

- The service catalog describes what is deployed and how to reach it. It does not replace `stack.yaml` (VM topology) or the health-probe catalog (probe mechanics).
- The catalog is environment-agnostic by default; per-environment overrides are in the `environments` field, not separate files.
- Service-to-service dependency graphs (which services call which) are out of scope for the first iteration; this catalog focuses on human and agent discovery, not runtime dependency management.

## Implementation Notes

- The original repository implementation was recorded in `0.69.0`; current-main completion and validation against the now-canonical health-probe, image, and secret catalogs are finalized in `0.72.0`.
- The current catalog covers all 19 services declared in [config/health-probe-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/health-probe-catalog.json).
- `make services` and `make show-service SERVICE=<id>` now provide the operator and agent query surface on top of the validated catalog.
- Validation now resolves [config/health-probe-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/health-probe-catalog.json), [config/image-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/image-catalog.json), [config/secret-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/secret-catalog.json), [config/uptime-kuma/monitors.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/uptime-kuma/monitors.json), and live topology inputs before merge.
