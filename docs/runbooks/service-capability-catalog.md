# Service Capability Catalog

## Purpose

`config/service-capability-catalog.json` is the operator-facing registry of platform services.

It answers:

- what the service is
- where it runs
- how operators reach it
- which runbook owns it
- which health probe, images, and secrets are attached to it
- which stage-scoped smoke suite should count as user-meaningful proof for each
  active environment
- which dependency failures are expected to degrade it and what the declared fallback mode is
- which redundancy declaration to consult in `config/service-redundancy-catalog.json`

## Update Rules

Update the catalog when:

1. a service is added or retired
2. its primary URL changes
3. its owning VM changes
4. its runbook or ADR changes
5. its health probe, image, or secret references change
6. its graceful-degradation declarations change
7. it needs an explicit stage smoke-suite override instead of the inherited
   default smoke proof
8. its redundancy declaration moves to a different VM, standby type, or recovery path

The catalog is the input for:

- `scripts/generate_ops_portal.py`
- `make services`
- `make show-service SERVICE=<id>`
- `scripts/service_redundancy.py`
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
- generated monitor bindings stay aligned with `config/health-probe-catalog.json`
- referenced health probes, images, and secrets exist
- degradation-mode declarations use valid dependency types, unique dependency ids per service, and `fault:*` verification references
- explicit `smoke_suites` overrides declare at least one receipt keyword or
  verification token, and active environments still resolve at least one smoke
  suite even when they inherit the repo-managed default
- active services match the canonical host/service topology where applicable

## Querying All Services

```bash
make services
```

## Querying One Service

```bash
make show-service SERVICE=grafana
```

This prints the lifecycle state, VM, URLs, health probe, image or secret references, degradation modes, runbook, dashboard, and tags for the selected service.

For active environments, `show-service` also prints the effective smoke-suite
contract and whether it is explicitly declared or inherited from the default
ADR 0251 rule.

For the redundancy tier, implemented redundancy claim, recovery objective, backup sources, failover metadata, and rehearsal evidence, query the paired catalog:

```bash
uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --service grafana
```
