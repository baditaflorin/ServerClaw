# ADR 0107: Platform Extension Model for Adding New Services

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.107.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-23

## Context

The platform has grown from a handful of services to 20+ through a process that can best be described as "add the service, then figure out what else it needs." The pattern works, but each addition requires an operator to remember all the integration points: service catalog entry, subdomain registration, health probe, Keycloak client, OpenBao policy, Grafana dashboard, Compose secrets, SLO definition, dependency graph entry, and now an API gateway registration.

The existing service scaffold generator (ADR 0078) generates role skeletons. It does not generate the cross-cutting integration artifacts. As a result:

- Some services have health probes (ADR 0064); others were added before that ADR and still don't
- Some services are in the API gateway catalog (ADR 0092); others were added before that catalog existed
- Some services have Grafana dashboards; most don't
- The dependency graph (ADR 0104) must be updated manually for every new service; it is easy to forget
- There is no checklist that an operator can follow to verify that a new service is fully integrated

The platform is a product. A product has a defined interface for extending it. Currently, "adding a new service" is an undocumented art. This ADR makes it a documented process.

## Decision

We will define a **platform extension checklist** as a machine-readable schema, enhance the scaffold generator (ADR 0078) to generate all required artifacts, and add a validation gate check that verifies every registered service has completed its checklist.

### The extension checklist

Every new service must complete the following before it is considered a first-class platform citizen:

| # | Artifact | Required | Scaffold generates |
|---|---|---|---|
| 1 | ADR | Yes | No (hand-written) |
| 2 | Ansible role (deploy + configure) | Yes | Skeleton only |
| 3 | Service capability catalog entry (`config/service-capability-catalog.json`) | Yes | Yes |
| 4 | Health probe definition (`config/health-probe-catalog.json`) | Yes | Yes |
| 5 | Subdomain entry (`config/subdomain-catalog.json`) | If public | Yes |
| 6 | API gateway catalog entry (`config/api-gateway-catalog.json`) | Yes | Yes |
| 7 | Dependency graph entries (`config/dependency-graph.json`) | Yes | Stub |
| 8 | Keycloak client registration | If OIDC | Yes (vars) |
| 9 | OpenBao policy and secrets definition (`config/secret-catalog.json`) | If has secrets | Yes (stub) |
| 10 | Grafana dashboard | Yes | Template |
| 11 | SLO definition (`config/slo-catalog.json`) | Yes | Stub |
| 12 | Compose secrets injection (`docker-compose.yml` pattern from ADR 0077) | If Compose service | Yes |
| 13 | Data catalog entry (`config/data-catalog.json`) | Yes | Yes |
| 14 | Alerting rules | Yes | Template |
| 15 | Runbook in `docs/runbooks/` | Yes | Template |

### Enhanced scaffold generator

`scripts/generate_service_scaffold.py` now backs the repo-managed `make scaffold-service` entry point and generates all artifacts in items 2–15:

```bash
make scaffold-service \
  NAME=my-service \
  TYPE=compose \
  VM=docker-runtime-lv3 \
  DEPENDS_ON=postgres,keycloak \
  OIDC=true
```

Output (generated files):

```
roles/my_service_runtime/
  tasks/main.yml          # skeleton Ansible tasks
  defaults/main.yml       # default vars
  meta/main.yml           # role dependencies
  README.md               # role documentation template

config/service-capability-catalog.json  [patched: my-service entry added]
config/health-probe-catalog.json        [patched: my-service probe added]
config/subdomain-catalog.json           [patched: my-service.lv3.org added]
config/api-gateway-catalog.json         [patched: /v1/my-service route added]
config/dependency-graph.json            [patched: stub edges for postgres, keycloak]
config/secret-catalog.json              [patched: my-service secrets stub]
config/slo-catalog.json                 [patched: my-service availability SLO stub]
config/data-catalog.json                [patched: my-service data store stub]

config/grafana/dashboards/my-service.json     [generated: template dashboard]
config/alertmanager/rules/my-service.yml      [generated: template alert rules]
docs/runbooks/configure-my-service.md         [generated: template runbook]
docs/adr/XXXX-my-service.md                  [generated: ADR template]
docs/workstreams/adr-XXXX-my-service.md       [generated: workstream template]
```

The generator writes template-backed stubs for all generated files. Operators fill in the stubs; the scaffold ensures nothing is forgotten.

### Completion validation

`scripts/validate_service_completeness.py` checks every service in `config/service-capability-catalog.json` against the checklist:

```python
def validate_service(service_id: str, catalogs: AllCatalogs) -> ValidationResult:
    issues = []

    if service_id not in catalogs.health_probes:
        issues.append(f"{service_id}: missing health probe definition")

    if service_id not in catalogs.api_gateway:
        issues.append(f"{service_id}: missing API gateway registration")

    if service_id not in catalogs.dependency_graph.nodes:
        issues.append(f"{service_id}: missing dependency graph node")

    if service_id not in catalogs.slo_catalog:
        issues.append(f"{service_id}: missing SLO definition")

    if service_id not in catalogs.grafana_dashboards:
        issues.append(f"{service_id}: missing Grafana dashboard")

    return ValidationResult(service=service_id, issues=issues)
```

This script is added to the validation gate (ADR 0087) as a required check. A push that adds a service to the capability catalog without completing all checklist items will fail the gate.

### Grandfathering existing services

For services already in the platform, the checklist creates a set of technical debt items. These are tracked in `config/service-completeness.json` with per-check suppression dates. Legacy suppressions expire on 2026-09-23, after which the same checklist blocks those services too.

### Documentation

The "Adding a New Service" runbook in the docs site (ADR 0094) is the primary reference:

1. Write the ADR
2. Run `make scaffold-service NAME=<name> ...`
3. Fill in all generated stubs (role tasks, dependency edges, secret names, dashboard panels, runbook content)
4. Run `lv3 validate --service <service_id>` to check completeness
5. Open the ADR workstream and proceed with the standard ADR implementation workflow

## Consequences

**Positive**
- Every new service is a first-class platform citizen from day one; nothing is missing by accident
- The scaffold generator eliminates the risk of forgetting integration points; the checklist is encoded in code, not in human memory
- The validation gate ensures incomplete services cannot reach `main`; technical debt on integration completeness is prevented by construction
- New operators can add services by following the documented process; institutional knowledge is not required

**Negative / Trade-offs**
- The scaffold generator produces stubs that must be completed; it reduces work but does not eliminate it; an incomplete stub that passes validation because the field exists but has placeholder content is a risk
- Grandfathering existing services creates a 6-month cleanup window; during this window, the validation gate has reduced coverage for legacy services
- The checklist will evolve as new ADRs add new required artifacts; the scaffold and validation script must be updated in sync

## Alternatives Considered

- **Keep the current ad-hoc process**: each new service teaches itself; works at low service count; fails at 30+ services when integration points are routinely missed
- **Pulumi or Crossplane component model**: infrastructure-as-code component libraries can enforce "complete" service definitions; over-engineered for this stack's Ansible/Compose base
- **A strict PR review checklist**: human checklist items get missed under time pressure; machine-enforced checklists do not

## Related ADRs

- ADR 0033: Declarative service topology catalog (service catalog is the extension registration point)
- ADR 0064: Health probe contracts (every service must have a probe)
- ADR 0078: Service scaffold generator (this ADR extends its scope significantly)
- ADR 0087: Repository validation gate (completeness validation is added as a gate check)
- ADR 0092: Unified platform API gateway (every service must register here)
- ADR 0096: SLO definitions (every service must have an SLO)
- ADR 0104: Service dependency graph (every service must declare its dependencies)
