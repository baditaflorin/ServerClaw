# ADR 0039: Shared Controller Automation Toolkit

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.42.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-22
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

## Implementation Notes

- The shared toolkit now lives in [scripts/controller_automation_toolkit.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/controller_automation_toolkit.py).
- The first toolkit surface includes repo-root and standard-path helpers, JSON and YAML loading or writing, Make target parsing, subprocess success wrappers, and consistent CLI error formatting.
- Existing controller-side scripts now consume the toolkit instead of repeating those primitives, including [scripts/workflow_catalog.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/workflow_catalog.py), [scripts/preflight_controller_local.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/preflight_controller_local.py), [scripts/live_apply_receipts.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/live_apply_receipts.py), [scripts/validate_repository_data_models.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repository_data_models.py), [scripts/generate_status_docs.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py), [scripts/uptime_kuma_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/uptime_kuma_tool.py), and [scripts/totp_provision.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/totp_provision.py).
- Operator and contributor guidance for the shared boundary is documented in [docs/runbooks/controller-automation-toolkit.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/controller-automation-toolkit.md).
