# Workstream ADR 0048: Command Catalog And Approval Gates

- ADR: [ADR 0048](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0048-command-catalog-and-approval-gates.md)
- Title: Safe execution contracts for remote mutation
- Status: live_applied
- Branch: `codex/adr-0048-command-catalog`
- Worktree: `../proxmox_florin_server-command-catalog`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0046-identity-classes`
- Conflicts With: none
- Shared Surfaces: remote commands, live-apply receipts, workflow execution, runbooks

## Scope

- define named command contracts for recurring mutating operations
- document dry-run, verification, and evidence expectations
- reduce dependence on free-form SSH mutation

## Non-Goals

- cataloging every historical command in this planning workstream
- removing break-glass shell access

## Expected Repo Surfaces

- `docs/adr/0048-command-catalog-and-approval-gates.md`
- `docs/workstreams/adr-0048-command-catalog.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `workstreams.yaml`

## Expected Live Surfaces

- recurring live mutation governed through named command contracts instead of free-form shell folklore
- approval attached to command ids, requester classes, and receipt planning rather than ad hoc shell review
- operator and assistant entrypoints routed through `make commands` and `make command-info`

## Verification

- `scripts/command_catalog.py --validate`
- `scripts/command_catalog.py --command configure-network`
- `scripts/command_catalog.py --check-approval --command configure-network --requester-class human_operator --approver-classes human_operator --validation-passed --preflight-passed --receipt-planned`
- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0048-command-catalog-and-approval-gates.md`
- `make validate-data-models`

## Merge Criteria

- the ADR makes named command contracts the steady-state model
- dry-run and evidence expectations are explicit

## Live Apply Notes

- Live apply completed on `2026-03-22` from `main`.
- Validation confirmed the command catalog is current on `main`, and the representative `configure-network` contract still resolves to the documented workflow, approval policy, verification path, and receipt requirement.
- Approval-gate evaluation confirmed the intended steady-state rule: recurring live mutation proceeds only when the requester and approver classes, validation, preflight, and receipt-planning conditions are satisfied.
