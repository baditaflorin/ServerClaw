# ADR 0211: Shared Policy Packs And Rule Registries

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

DRY is usually lost through repeated policy decisions, not just repeated code
syntax. Thresholds, naming rules, eligibility checks, approval boundaries, and
placement logic often reappear in scripts, playbooks, dashboards, docs, and
tests as copied constants or slightly different `if` chains.

That duplication makes the platform inconsistent:

- two tools can claim to enforce the same rule but mean different things
- updates require many edits and still miss corners
- architectural intent becomes impossible to audit quickly

## Decision

We will centralize shared platform policies into reusable policy packs or rule
registries instead of re-copying policy logic across delivery surfaces.

A shared policy pack should hold things such as:

- thresholds and budgets
- eligibility and approval rules
- naming and classification conventions
- retention and recovery rules
- capability support matrices

Consumers should import or render from the shared policy source. If a policy
must be materialized into generated files, the generated artifact should point
back to the governing source rather than becoming a second hand-edited truth.

## Consequences

**Positive**

- one policy change can propagate consistently across tooling, docs, and tests
- reviews can focus on the rule itself instead of hunting for every duplicated
  implementation
- self-correction loops gain stable rule inputs instead of bespoke conditionals

**Negative / Trade-offs**

- central policy packs need careful naming and ownership so they do not turn
  into a dumping ground
- some local exceptions will need explicit override mechanisms instead of hidden
  divergence

## Boundaries

- This ADR centralizes policy, not all data. Context-specific inputs can still
  live near the consuming service.
- A rule registry is not a license for unreadable indirection; if a policy is
  trivial and truly local, keep it local.
- Duplicate policy text in explanatory docs is acceptable if the canonical
  source remains machine-checkable and the docs are clearly derived.

## Related ADRs

- ADR 0063: Centralized vars and computed facts library
- ADR 0064: Health probe contracts
- ADR 0179: Service redundancy tier matrix
- ADR 0180: Standby capacity reservation and placement rules
