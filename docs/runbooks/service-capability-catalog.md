# Service Capability Catalog

## Purpose

`config/service-capability-catalog.json` is the operator-facing registry of platform services.

It answers:

- what the service is
- where it runs
- how operators reach it
- which runbook owns it
- which health probe, images, and secrets are attached to it

## Update Rules

Update the catalog when:

1. a service is added or retired
2. its primary URL changes
3. its owning VM changes
4. its runbook or ADR changes
5. its health probe, image, or secret references change

The catalog is the input for:

- `scripts/generate_ops_portal.py`
- `make services`
- `make show-service SERVICE=<id>`
- future CLI and agent discovery surfaces

## Validation

Run:

```bash
uv run --with pyyaml --with jsonschema python scripts/service_catalog.py --validate
```

Or use:

```bash
make validate
```

Validation checks:

- JSON Schema validity and required fields
- unique service ids and names
- coverage for every service in `config/health-probe-catalog.json`
- runbook paths exist
- referenced Uptime Kuma monitors exist
- referenced health probes, images, and secrets exist
- active services match the canonical host/service topology where applicable

## Querying All Services

```bash
make services
```

## Querying One Service

```bash
make show-service SERVICE=grafana
```

This prints the lifecycle state, VM, URLs, health probe, image or secret references, runbook, dashboard, and tags for the selected service.
