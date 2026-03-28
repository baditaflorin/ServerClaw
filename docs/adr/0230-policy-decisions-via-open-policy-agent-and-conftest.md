# ADR 0230: Policy Decisions Via Open Policy Agent And Conftest

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

The platform already has validation scripts, command approval rules, and policy
concepts, but policy evaluation is still too fragmented across:

- Python helpers
- shell scripts
- workflow-specific logic
- human judgment in interactive sessions

That makes it harder for the server to make the same decision the authoring
client would have made.

## Decision

We will use **Open Policy Agent (OPA)** as the shared decision engine and
**Conftest** as the config-and-pipeline policy runner.

### Policy scope

OPA and Conftest should evaluate policy for:

- environment boundary checks
- allowed command and workflow use
- required approvals
- release promotion eligibility
- service and topology invariants
- bundle and artifact admission

### Architecture rule

- policy is authored once in Rego
- callers such as Gitea, Windmill, CLI wrappers, and reconcile loops query or
  execute that shared policy instead of re-encoding the same rule differently
- enforcement remains in the caller, but decision logic becomes shared

## Consequences

**Positive**

- Server-side automation can make consistent decisions without depending on a
  laptop-local script path.
- Policy becomes easier to test and audit.
- A mature policy engine replaces hand-rolled condition duplication.

**Negative / Trade-offs**

- Rego introduces another language and toolchain into the platform.
- Teams will need discipline to avoid scattering "temporary" bypass logic around
  the shared engine.

## Boundaries

- OPA decides; it does not perform the action.
- This ADR does not retire existing validators immediately. It defines the
  target shared policy direction.

## Related ADRs

- ADR 0031: Repository validation pipeline
- ADR 0048: Command catalog and approval gates
- ADR 0168: Automated validation gate
- ADR 0213: Architecture fitness functions in the validation gate
- ADR 0224: Server-resident operations as the default control model
