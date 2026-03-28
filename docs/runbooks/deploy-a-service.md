# Deploy a Service

This runbook covers the repository-first path for deploying or updating one LV3 service.

## Preconditions

- the service definition is already represented in `config/service-capability-catalog.json`
- the service redundancy declaration is current in `config/service-redundancy-catalog.json`
- the owning ADR and workstream are current
- required controller-local secrets are available
- `make validate` passes from the branch you intend to promote

## Procedure

1. Confirm the service topology, catalog metadata, runbook, and health probe contract are committed.
2. Run the relevant syntax or unit checks for the service workstream.
3. If the change publishes or changes a hostname, verify the subdomain catalog entry and edge-publication intent before rollout.
4. Promote the change through the repo’s normal merge path to `main`.
5. Check whether ADR 0191 governs the guest behind the service:

```bash
make immutable-guest-replacement-plan service=<service-id>
```

6. If the service is not governed by immutable guest replacement, apply the bounded live automation from `main` with the usual workflow for that service. The live-apply target runs the ADR 0179 redundancy preflight before Ansible starts.
7. If the service is governed by ADR 0191, use the immutable guest replacement path first. Only use in-place mutation for a documented narrow exception, and set `ALLOW_IN_PLACE_MUTATION=true` when you intentionally take that exception.
8. Verify health, endpoint reachability, and any expected dashboard or probe signals.
9. Record or update the live-apply receipt, including any ADR 0191 exception, and update the workstream status.

## Related runbooks

- [Environment promotion pipeline](environment-promotion-pipeline.md)
- [Immutable guest replacement](immutable-guest-replacement.md)
- [Validation gate](validation-gate.md)
- [Service capability catalog](service-capability-catalog.md)
- [Service redundancy tier matrix](service-redundancy-tier-matrix.md)
