# ADR 0225: Server-Resident Reconciliation Via Ansible Pull

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.43
- Implemented In Platform Version: 0.130.40
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

The current repo automation is strong at describing desired state, but actual
reconciliation still leans too heavily on controller-side push execution.

That keeps the platform dependent on an external operator session for routine
convergence. It also blurs the line between design authority and execution
authority.

## Decision

We will use **`ansible-pull`** as the default server-resident reconcile
primitive for host and service surfaces that can safely converge from a local
checkout.

### Operating model

- a designated server-side checkout pulls from the merged control repository or
  from an approved release bundle source
- `ansible-pull` runs locally against `localhost` or the declared inventory
  slice for that node's responsibility
- runs are scheduled or event-triggered from the server side rather than pushed
  interactively from a workstation

### Safety rules

- only merged `main`, approved release tags, or explicitly declared staging refs
  may feed the server-resident pull loop
- local pull runs must emit receipts and logs back into the platform evidence
  path
- the pull runner may not invent drift fixes outside the repo-defined playbooks
  and catalogs

### Why this tool

`ansible-pull` keeps the existing Ansible investment, inverts the push model in
a mature and well-understood way, and avoids introducing a full new agent
ecosystem just to make the platform capable of converging itself.

## Consequences

**Positive**

- The platform can reconcile from inside the platform boundary.
- Existing Ansible roles and catalogs stay reusable.
- The split between authored desired state and executed desired state becomes
  clearer.

**Negative / Trade-offs**

- Local pull checkouts become operational state and need governance.
- Not every workflow belongs in `ansible-pull`; event-driven and multi-step
  orchestration still need other runtimes.

## Boundaries

- `ansible-pull` is for reconciliation, not for arbitrary user shell sessions.
- This ADR does not replace first-boot provisioning or break-glass repair when
  git, package, or network prerequisites are missing.

## Related ADRs

- ADR 0030: Ansible role interface contracts
- ADR 0048: Command catalog and approval gates
- ADR 0143: Gitea for self-hosted git and CI
- ADR 0168: Automated validation gate
- ADR 0224: Server-resident operations as the default control model
