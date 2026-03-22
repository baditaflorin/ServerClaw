# ADR 0035: Workflow Catalog And Machine-Readable Execution Contracts

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The repository now has several execution surfaces:

- `Makefile` targets
- Ansible playbooks
- repo-local scripts
- preflight workflow ids
- runbooks that describe when to use each path

Those pieces are getting stronger, but the contract is still spread across several files.

That creates agentic and maintainability gaps:

- assistants cannot discover the full workflow surface from one machine-readable source
- preflight workflow ids, Make targets, and runbook names can drift
- it is hard to answer simple questions such as which command is the preferred entry point for a capability
- future automation such as dashboards, CLIs, or assistant tooling cannot render or validate workflow metadata directly

## Decision

We will define one workflow catalog as the canonical machine-readable contract for repository execution paths.

The catalog will describe, at minimum:

1. Workflow id and human purpose.
2. Preferred entry point such as `make`, script, or direct playbook.
3. Required preflight id and validation expectations.
4. Live-impact classification such as repo-only, host-live, or guest-live.
5. Primary outputs, verification commands, and owning runbook.

## Consequences

- Assistants can discover the operating surface without inferring it from prose.
- Drift between Make targets, preflight ids, and runbooks becomes easier to detect automatically.
- Future generated docs or CLIs can render workflow help from the same source of truth.
- The first implementation must stay descriptive and avoid turning the catalog into a second orchestration engine.
