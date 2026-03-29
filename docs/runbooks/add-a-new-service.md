# Add A New Service

This runbook is the human-oriented entry point for extending the platform with a new managed service.

ADR 0107 makes new-service integration an explicit repository contract rather than an ad hoc checklist in somebody's head.

## Formal Process

1. Write the ADR.
   Create the service ADR first so the decision, runtime model, and risks exist before any scaffolded files do.
2. Define the capability contract first when the service introduces or replaces a critical shared product surface.
   Update `config/capability-contract-catalog.json` before locking in a new identity provider, workflow engine, secret authority, topology system, or similar shared capability choice.
3. Run the scaffold.

```bash
make scaffold-service \
  NAME=my-service \
  TYPE=compose \
  VM=docker-runtime-lv3 \
  DEPENDS_ON=postgres,keycloak \
  OIDC=true
```

4. Fill the generated stubs.
   Complete the role, playbooks, catalog entries, dependency edges, SLO description, dashboard, alert rules, runbook, and any generated ADR/workstream placeholders.
5. Run the completeness check.

```bash
lv3 validate --service my_service
```

6. Run the repo validation flow and continue the workstream normally.

```bash
make validate-data-models
make validate
```

## What The Scaffold Adds

- service capability catalog entry
- health probe definition
- subdomain entry when a hostname is declared
- API gateway route stub
- dependency graph node and dependency edges
- secret catalog stub
- SLO stub
- data catalog stub
- Grafana dashboard template
- alert rule template
- runbook template
- service completeness profile for ADR 0107 validation

## Grandfathering Model

Services that pre-date ADR 0107 are tracked in `config/service-completeness.json` with per-check suppressions that expire on `2026-09-23`.

New scaffolded services do not receive those suppressions. Missing checklist items for a new service block `lv3 validate --service <id>` and the validation gate.

## Related Runbooks

- [Scaffold new service](scaffold-new-service.md)
- [Capability contract catalog](capability-contract-catalog.md)
- [Service capability catalog](service-capability-catalog.md)
- [Subdomain governance](subdomain-governance.md)
- [Health probe contracts](health-probe-contracts.md)
