# ADR 0060: Open WebUI For Operator And Agent Workbench

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The platform is accumulating structured state, workflows, receipts, dashboards, and future internal APIs, but there is no single workbench where a human can:

- ask for platform context
- inspect approved knowledge sources
- hand work to an agent
- review agent output
- invoke governed tools without falling back to raw shell

## Decision

We will add an internal operator-and-agent workbench using Open WebUI or an equivalent repo-managed LLM console.

Initial expectations:

1. the workbench is private-only
2. model access is mediated through approved connectors, not arbitrary outbound calls
3. exposed tools are limited to governed surfaces such as workflow catalog queries, receipt lookups, status docs, and approved execution endpoints
4. user and bot identities follow the shared SSO and approval model where available

Initial use cases:

- answer operational questions from repo and platform metadata
- draft or review routine changes before execution
- summarize alerts, logs, traces, and receipts for humans
- coordinate with workflow runners instead of invoking broad shell access directly

## Consequences

- Humans gain a central conversational workbench tied to the platform’s approved data and tool surfaces.
- Agents become easier to supervise because tool access can be narrowed to named operations.
- Model governance, prompt hygiene, and data-boundary rules become platform concerns.
- The workbench itself becomes a sensitive operator surface and must be isolated accordingly.

## Boundaries

- The workbench must not expose unrestricted root shell or arbitrary network egress.
- It is an orchestration and review surface, not the source of truth for infrastructure design.
- Any mutating action still follows the command-catalog, approval, and evidence rules.
