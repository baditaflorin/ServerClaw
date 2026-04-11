# Command Catalog And Approval Gates

## Purpose

This runbook defines the canonical mutating command-contract catalog and the approval checks that must be satisfied before recurring live mutation.

## Canonical Sources

- command catalog: [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/command-catalog.json)
- catalog CLI: [scripts/command_catalog.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/command_catalog.py)
- shared approval policy: [policy/decisions/command_approval.rego](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/policy/decisions/command_approval.rego)
- shared policy validator: [scripts/policy_checks.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/policy_checks.py)
- workflow catalog dependency: [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/workflow-catalog.json)
- receipt model: [docs/runbooks/live-apply-receipts-and-verification-evidence.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/live-apply-receipts-and-verification-evidence.md)

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

Validate the shared ADR 0230 policy bundle before changing callers or replaying
worker automation:

```bash
python3 scripts/policy_checks.py --validate
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

The approval check also emits a structured mutation-audit event when ADR 0066 sink settings are configured. Override the default event identity when needed:

```bash
scripts/command_catalog.py \
  --check-approval \
  --command configure-network \
  --requester-class human_operator \
  --approver-classes human_operator \
  --validation-passed \
  --preflight-passed \
  --receipt-planned \
  --audit-correlation-id change-20260322-001 \
  --audit-actor-id ops
```

ADR 0230 routes the approval decision itself through the shared OPA policy
bundle, so controller-side CLIs and worker-side Windmill wrappers receive the
same approval result, reasons, workflow id, and receipt requirement.

Dry-run the bounded execution envelope for one governed command without
executing it:

```bash
python3 scripts/governed_command.py \
  --command network-impairment-matrix \
  --requester-class human_operator \
  --approver-classes human_operator \
  --validation-passed \
  --preflight-passed \
  --receipt-planned \
  --param NETWORK_IMPAIRMENT_MATRIX_ARGS='target_class=staging --approve-risk' \
  --dry-run
```

## Operating Rule

Before a recurring live mutation is executed:

1. confirm the workflow entry point through [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/workflow-catalog.json)
2. confirm the approval policy, operator inputs, and rollback guidance through [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/command-catalog.json)
3. confirm the command execution profile, timeout, working directory, and effective user through the command catalog execution block
4. run the controller-local preflight when the workflow requires it
5. run `python3 scripts/policy_checks.py --validate` and then `make validate` against the repo state that will be applied
6. plan the live-apply receipt before executing the mutating command
7. execute the live mutation through the bounded wrapper instead of calling the Make target inline from the controller shell

If a mutating action is recurring but is not represented in the command catalog, it is not yet an approved steady-state execution surface.

## Notes

- The workflow catalog still owns entry points, runbooks, validation targets, and verification commands.
- ADR 0230 keeps the approval decision logic in `policy/decisions/command_approval.rego`, while `scripts/command_catalog.py` remains the caller-facing contract and CLI surface.
- The command catalog layers approval and mutation-specific contract data on top of those workflows, including the bounded execution profile used by ADR 0227.
- Blocked workflows remain present in the command catalog so assistants and operators can see that the path exists but is intentionally not executable.
