# ADR 0122: Windmill Operator Access Admin Surface

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.120.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

ADR 0108 established a governed operator onboarding and off-boarding workflow backed by `config/operators.yaml`, `scripts/operator_manager.py`, and Windmill wrapper scripts. That workflow is sound, but the practical operator experience is still terminal-first:

- adding an operator requires `make operator-onboard ...` or `lv3 operator add ...`
- removing an operator requires `make operator-offboard ...`
- inventory and reconciliation require separate CLI commands
- a new operator workstation has no browser-first admin path for routine access changes

This is acceptable for one maintainer but weak for shared operations. The platform already runs Windmill as the approved workflow surface. Replacing it with a second internal-tool product would duplicate identity, deployment, and audit concerns that are already solved in-repo.

The missing layer is a browser-based admin surface that:

1. reuses the ADR 0108 workflow contract instead of bypassing it
2. can be deployed and versioned from the repository
3. exposes a simple operator roster, onboarding form, off-boarding form, and reconciliation action
4. works from a fresh machine with only browser access to Windmill

## Decision

We will add a **repo-managed Windmill raw app** that acts as the operator access admin console for ADR 0108.

### Scope of the admin surface

The app will provide:

- operator roster listing from `config/operators.yaml`
- create-operator form that calls the governed `operator-onboard` wrapper
- off-board action that calls the governed `operator-offboard` wrapper
- roster reconciliation action that calls `sync-operators`
- per-operator access inventory lookup through the existing inventory workflow

### Implementation model

The app is not allowed to embed access-management logic directly in the frontend. It must call repo-managed Windmill scripts that in turn invoke:

- `scripts/operator_manager.py`
- `scripts/operator_access_inventory.py`
- `config/operators.yaml`

This preserves one source of truth for:

- role mapping
- Keycloak/OpenBao/Tailscale provisioning logic
- audit emission
- bootstrap password generation

### Deployment contract

The admin console will be stored under `config/windmill/apps/` in the repository as a raw app bundle and seeded into the `lv3` workspace by the `windmill_runtime` role.

The same role that currently seeds repo-managed Windmill scripts will also:

1. copy the raw app bundle to the Windmill host
2. invoke the Windmill CLI from the repo-managed runtime image
3. push the raw app into the `lv3` workspace

### Security boundary

The app remains a Windmill-private surface. It is not exposed anonymously and it does not replace the `ops.lv3.org` portal. It is an authenticated administrative UI inside the existing Windmill access boundary.

### UX boundary

This ADR adds a browser-first admin path inside Windmill. It does not attempt to redesign the entire ops portal or move all identity administration into `ops.lv3.org`.

## Consequences

**Positive**

- operator creation and removal gain a browser-first path with no terminal requirement
- the same governed backend remains in control, so there is no policy drift between UI and CLI
- the app is versioned, tested, and deployed from the repo like the rest of the platform
- a new machine can perform routine access administration through Windmill after normal SSO login

**Negative / Trade-offs**

- the app depends on the Windmill runtime and workspace seeding contract remaining healthy
- the frontend is another repo-managed surface that needs validation when Windmill app conventions change
- access management is still inside Windmill rather than embedded directly into the ops portal

## Boundaries

- This ADR does not introduce self-service end-user sign-up.
- This ADR does not replace Keycloak as the identity authority.
- This ADR does not expose a public user-management endpoint.
- This ADR does not change ADR 0108 role semantics or secret handling.

## Related ADRs

- ADR 0044: Windmill for agent and operator workflows
- ADR 0056: Keycloak for operator and agent SSO
- ADR 0066: Structured mutation audit log
- ADR 0093: Interactive ops portal
- ADR 0108: Operator onboarding and off-boarding workflow
