# Controller Automation Toolkit

## Purpose

This runbook describes the shared controller-side Python helpers used by repo-local automation scripts.

## Toolkit Boundary

The shared toolkit lives in [scripts/controller_automation_toolkit.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/controller_automation_toolkit.py).

It provides small reusable primitives for:

- repo-root and standard-path helpers
- JSON and YAML loading or writing
- Make target parsing
- subprocess success checks for repo-local verification
- consistent CLI error formatting

It is intentionally not an orchestration framework. Workflow-specific logic should stay in the script that owns the workflow.

## Current Consumers

The toolkit is used by repo-local controller scripts including:

- [scripts/workflow_catalog.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/workflow_catalog.py)
- [scripts/preflight_controller_local.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/preflight_controller_local.py)
- [scripts/live_apply_receipts.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/live_apply_receipts.py)
- [scripts/validate_repository_data_models.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repository_data_models.py)
- [scripts/generate_status_docs.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py)
- [scripts/uptime_kuma_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/uptime_kuma_tool.py)
- [scripts/totp_provision.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/totp_provision.py)

## Change Rules

- add shared behavior to the toolkit only after it appears in more than one script or clearly belongs to the standard controller contract
- keep workflow-specific validation, API calls, and command semantics out of the toolkit
- when a new shared primitive is added, update this runbook and at least one consuming script in the same change
- prefer refactoring existing duplication into the toolkit over adding a second ad hoc helper in another script
