# Break-Glass Recovery

Use this runbook only for outages, lockouts, or control-plane failures where the normal named-operator path cannot restore service quickly enough.

## Rules

- prefer repo-managed recovery workflows over ad hoc shell changes
- keep the scope narrow and reversible
- document the exact manual actions immediately if automation could not be used
- rotate or revoke any emergency credential material after the incident

## Procedure

1. Establish the failure domain: host access, edge publication, identity, secrets, storage, or application runtime.
2. Recover the minimum access path needed to restore controlled automation.
3. Apply the bounded recovery workflow for the affected surface.
4. Verify the restored service and dependent surfaces.
5. Record the incident, recovery actions, and any required follow-up remediation.

## Related runbooks

- [Control plane recovery](configure-control-plane-recovery.md)
- [Initial access](initial-access.md)
- [Identity taxonomy and managed principals](identity-taxonomy-and-managed-principals.md)
