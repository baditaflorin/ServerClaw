# Command Catalog And Approval Gates

## Purpose

This runbook defines the canonical mutating command-contract catalog and the approval checks that must be satisfied before recurring live mutation.

## Canonical Sources

- command catalog: [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/command-catalog.json)
- catalog CLI: [scripts/command_catalog.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/command_catalog.py)
- workflow catalog dependency: [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json)
- receipt model: [docs/runbooks/live-apply-receipts-and-verification-evidence.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/live-apply-receipts-and-verification-evidence.md)

The command catalog is the source of truth for:

- mutating command ids that are allowed as recurring execution surfaces
- approval policy attached to each named command
- required human or agent requester classes
- explicit operator inputs and preconditions
- evidence expectations and failure guidance

## Primary Commands

List the command catalog:

```bash
make commands
```

Show one command contract:

```bash
make command-info COMMAND=configure-network
```

Validate the command catalog directly:

```bash
scripts/command_catalog.py --validate
```

Evaluate an approval gate for a planned live change:

```bash
scripts/command_catalog.py \
  --check-approval \
  --command configure-network \
  --requester-class human_operator \
  --approver-classes human_operator \
  --validation-passed \
  --preflight-passed \
  --receipt-planned
```

## Operating Rule

Before a recurring live mutation is executed:

1. confirm the workflow entry point through [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json)
2. confirm the approval policy, operator inputs, and rollback guidance through [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/command-catalog.json)
3. run the controller-local preflight when the workflow requires it
4. run `make validate` against the repo state that will be applied
5. plan the live-apply receipt before executing the mutating command

If a mutating action is recurring but is not represented in the command catalog, it is not yet an approved steady-state execution surface.

## Notes

- The workflow catalog still owns entry points, runbooks, validation targets, and verification commands.
- The command catalog layers approval and mutation-specific contract data on top of those workflows.
- Blocked workflows remain present in the command catalog so assistants and operators can see that the path exists but is intentionally not executable.
