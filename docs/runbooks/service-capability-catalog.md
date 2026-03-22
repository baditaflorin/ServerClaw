# Service Capability Catalog

## Purpose

`config/service-capability-catalog.json` is the operator-facing registry of platform services.

It answers:

- what the service is
- where it runs
- how operators reach it
- which runbook owns it
- which portal card and VM row it should appear in

## Update Rules

Update the catalog when:

1. a service is added or retired
2. its primary URL changes
3. its owning VM changes
4. its runbook or ADR changes
5. its Uptime Kuma monitor name changes

The catalog is the input for:

- `scripts/generate_ops_portal.py`
- `make show-service SERVICE=<id>`
- future CLI and agent discovery surfaces

## Validation

Run:

```bash
python3 scripts/service_catalog.py --validate
```

Or use:

```bash
make validate
```

Validation checks:

- schema version and required fields
- unique service ids and names
- runbook paths exist
- referenced Uptime Kuma monitors exist
- active services match the canonical host/service topology where applicable

## Querying One Service

```bash
make show-service SERVICE=grafana
```

This prints the lifecycle state, VM, URLs, runbook, dashboard, and tags for the selected service.
