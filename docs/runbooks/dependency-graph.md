# Dependency Graph Operations

## Purpose

This runbook covers the repository-managed service dependency graph introduced by [ADR 0104](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0104-service-dependency-graph.md).

Use it when you need to:

- validate that `config/dependency-graph.json` still matches the service catalog
- inspect the blast radius of a service failure
- regenerate the Mermaid dependency diagram for the docs tree
- confirm deployment order for a set of mutually dependent services

## Validate

Run the canonical validator:

```bash
uv run --with jsonschema python scripts/validate_dependency_graph.py
```

This checks:

- JSON schema compliance against `docs/schema/service-dependency-graph.schema.json`
- one graph node per service in `config/service-capability-catalog.json`
- no unknown services in the graph
- no hard-dependency cycles
- recovery tiers match the hard-dependency ordering

## Inspect Failure Impact

For operator-friendly output:

```bash
lv3 impact postgres
```

For the lower-level script output:

```bash
uv run --with jsonschema python scripts/dependency_impact.py --service postgres
```

Both commands show:

- direct hard failures
- transitive hard failures
- direct soft degradations
- startup-only and read-path dependencies

## Regenerate The Diagram

Write the generated Markdown page:

```bash
uv run --with jsonschema python scripts/generate_dependency_diagram.py --write
```

Validate the committed page without rewriting it:

```bash
uv run --with jsonschema python scripts/generate_dependency_diagram.py --check
```

The generated file is:

- `docs/site-generated/architecture/dependency-graph.md`

## Validate The Full Repo Surface

These dependency-graph checks are part of the normal repository validation paths:

```bash
make validate-data-models
make validate-generated-docs
```

The remote validation gate also includes the dedicated `dependency-graph` check in `config/validation-gate.json`.

## Deployment Order

`scripts/promotion_pipeline.py` now exports `deployment_order()` for dependency-aware sequencing. Use it from Python if you need to inspect a candidate release order:

```bash
python3 - <<'PY'
import promotion_pipeline
print(promotion_pipeline.deployment_order(["ops_portal", "keycloak", "postgres"]))
PY
```

Expected output:

```text
['postgres', 'keycloak', 'ops_portal']
```
