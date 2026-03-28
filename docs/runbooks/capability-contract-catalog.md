# Capability Contract Catalog

This runbook turns ADR 0205 into a concrete repository workflow.

`config/capability-contract-catalog.json` is the contract-first registry for critical shared platform capabilities such as identity, workflow execution, secret authority, topology inventory, and private access.

## Use This When

- introducing a new critical shared product
- replacing an existing critical shared product
- tightening the non-functional contract for a shared capability before product reevaluation

## Required Flow

1. Define or update the capability contract in `config/capability-contract-catalog.json`.
2. Record the contract requirements before approving a product ADR or changing the current product selection.
3. Point the contract at the selected service, ADR, and runbook only after the capability definition is complete.
4. Regenerate dependent artifacts and re-run validation.

The contract must capture:

- required outcomes and service guarantees
- canonical inputs and outputs
- security, audit, and observability expectations
- portability constraints
- import or export expectations for migration
- failure modes and acceptable degradation behaviour

## Inspect The Catalog

List all capability contracts:

```bash
make capability-contracts
```

Show one contract:

```bash
make capability-contract-info CAPABILITY=identity_provider
```

Direct script entrypoints are also available:

```bash
uv run --with pyyaml --with jsonschema python scripts/capability_contracts.py --list
uv run --with pyyaml --with jsonschema python scripts/capability_contracts.py --contract workflow_orchestrator
```

## Validate

Run the dedicated validator:

```bash
uv run --with pyyaml --with jsonschema python scripts/capability_contracts.py --validate
```

Then run the broader repo gates that consume the catalog:

```bash
make validate-data-models
make generate-platform-manifest
make validate-generated-portals
```

## Operator Notes

- The catalog is intentionally separate from `config/service-capability-catalog.json`. Services describe what is deployed; capability contracts describe what a critical shared surface must do before any one product is chosen.
- If a future capability has a defined contract but no approved product yet, omit `current_selection` until the product ADR is accepted.
- The interactive ops portal and the platform manifest both surface this catalog after the `ops_portal` runtime is converged.
