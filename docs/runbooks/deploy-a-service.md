# Deploy a Service

This runbook covers the repository-first path for deploying or updating one LV3 service.

## Preconditions

- the service definition is already represented in `config/service-capability-catalog.json`
- the owning ADR and workstream are current
- required controller-local secrets are available
- `make validate` passes from the branch you intend to promote

## Procedure

1. Confirm the service topology, catalog metadata, runbook, and health probe contract are committed.
2. Run the relevant syntax or unit checks for the service workstream.
3. If the change publishes or changes a hostname, verify the subdomain catalog entry and edge-publication intent before rollout.
4. Promote the change through the repo’s normal merge path to `main`.
5. Apply the live automation from `main` with the bounded workflow for that service.
6. Verify health, endpoint reachability, and any expected dashboard or probe signals.
7. Record or update the live-apply receipt and workstream status.

## Related runbooks

- [Environment promotion pipeline](environment-promotion-pipeline.md)
- [Validation gate](validation-gate.md)
- [Service capability catalog](service-capability-catalog.md)
