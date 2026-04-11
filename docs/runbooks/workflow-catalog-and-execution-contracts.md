# Workflow Catalog And Execution Contracts

## Purpose

This runbook defines the canonical machine-readable workflow catalog for repository execution paths.

## Canonical Sources

- workflow catalog: [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/workflow-catalog.json)
- catalog CLI: [scripts/workflow_catalog.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/workflow_catalog.py)
- command catalog overlay: [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/command-catalog.json)
- preferred command surface: [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/Makefile)

The workflow catalog is the source of truth for:

- workflow ids and descriptions
- preferred entry points
- controller-local preflight requirements
- validation expectations
- live-impact classification
- execution class (`mutation` or `diagnostic`)
- per-workflow budget overrides merged with `config/workflow-defaults.yaml`
- owning runbooks and verification commands

Approval policy, operator inputs, evidence planning, and failure guidance for mutating workflows now live in the separate [command catalog runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/command-catalog-and-approval-gates.md).

## Primary Commands

List the catalog:

```bash
make workflows
```

Show one workflow:

```bash
make workflow-info WORKFLOW=converge-monitoring
```

Validate the catalog directly:

```bash
scripts/workflow_catalog.py --validate
```

## Operating Rule

When adding or changing a workflow entry point:

1. update the preferred Make target or script
2. update [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/workflow-catalog.json)
3. update any required controller-local secret ids through the workflow catalog and [config/controller-local-secrets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/controller-local-secrets.json)
4. update `execution_class` and any budget overrides when the workflow runtime characteristics changed
5. update the owning runbook

Do not add new long-running entry points only in prose. They should be represented in the catalog.
