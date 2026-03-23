# Add a New Service

This runbook is the human-oriented entry point for extending the platform with a new managed service.

## Procedure

1. Create or claim the ADR and workstream for the new service.
2. Use the scaffold flow where applicable so the baseline role, playbook, runbook, and catalog entries stay consistent.
3. Fill in the service capability catalog, health probe, subdomain, secret, and image metadata instead of leaving placeholder values behind.
4. Add or update the service-specific runbook before merge.
5. Validate the repository and the service-specific playbook syntax.
6. Merge to `main`, then apply from `main` only after the publication and secret preconditions are satisfied.

## Related runbooks

- [Scaffold new service](scaffold-new-service.md)
- [Service capability catalog](service-capability-catalog.md)
- [Subdomain governance](subdomain-governance.md)
- [Health probe contracts](health-probe-contracts.md)
