# Workstream ADR 0048: Command Catalog And Approval Gates

- ADR: [ADR 0048](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0048-command-catalog-and-approval-gates.md)
- Title: Safe execution contracts for remote mutation
- Status: merged
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

- a smaller blast radius for agent-driven mutation
- reviewable execution contracts instead of shell folklore

## Verification

- `scripts/command_catalog.py --validate`
- `scripts/command_catalog.py --command configure-network`
- `scripts/command_catalog.py --check-approval --command configure-network --requester-class human_operator --approver-classes human_operator --validation-passed --preflight-passed --receipt-planned`
- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0048-command-catalog-and-approval-gates.md`

## Merge Criteria

- the ADR makes named command contracts the steady-state model
- dry-run and evidence expectations are explicit

## Notes For The Next Assistant

- the repo now has a machine-readable command-contract layer separate from the broader workflow catalog
- use this ADR before granting broader agent mutation rights
- this workstream is implemented on `main` as a repo-only change; no live platform apply is pending
