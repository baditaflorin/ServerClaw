# Workstream ws-0297-main-merge: Integrate ADR 0297 Live Apply Into `main`

- ADR: [ADR 0297](../adr/0297-renovate-bot-as-the-automated-stack-version-upgrade-proposer.md)
- Title: Integrate Renovate automation live-apply changes and follow-up receipts into main
- Status: merged
- Included In Repo Version: 0.177.126
- Live Applied In Platform Version: 0.130.74
- Implemented On: 2026-03-31
- Merged On: 2026-04-01
- Branch: `codex/ws-0297-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0297-main-merge`
- Source Branch: `codex/ws-0297-live-apply-r2`
- Owner: codex

## Summary

- merge the ADR 0297 live-apply workstream into `main`, refresh release artifacts, and bump the repo version to `0.177.126`
- record build-server workspace cleanup evidence and update the validation runbook with a disk-recovery troubleshooting step

## Verification

- `make pre-push-gate` succeeded on the merge branch after the build-server workspace cleanup.
- `bash scripts/validate_repo.sh agent-standards generated-docs generated-portals` completed successfully on the merge branch.
