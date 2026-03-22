# ADR 0039: Shared Controller Automation Toolkit

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The repository now has several controller-side scripts and local contracts:

- validation tooling
- preflight checks
- Uptime Kuma management
- workstream creation helpers
- local path conventions under `.local/`

As more controller-side automation is added, helper logic will start repeating:

- repo-root detection
- path and artifact resolution
- loading machine-readable repo data
- consistent error formatting
- safe command execution and result reporting

Without a shared toolkit, agent-facing scripts will drift in style and behavior.

## Decision

We will define one shared controller automation toolkit for repo-local scripts.

The toolkit should provide, at minimum:

1. Repo-root and standard-path helpers.
2. Shared loaders for canonical manifests and catalogs.
3. Consistent CLI error and result formatting.
4. Reusable wrappers for subprocess execution and verification reporting.
5. A clear boundary between shared primitives and workflow-specific commands.

## Consequences

- New controller-side tools become cheaper to add and easier to review.
- Agent-written scripts share one predictable operating style.
- Machine-readable repo contracts become easier to consume from code instead of ad hoc parsing.
- The toolkit must stay small and pragmatic; it should remove duplication, not introduce an unnecessary framework.
