# Workstream ws-0377-repo-intake-subdomain: Repo Intake as First-Class Subdomain

- ADR: [ADR 0224](../adr/0224-self-service-repo-intake-and-agent-assisted-deployments.md)
- Title: repo-intake as a first-class subdomain
- Status: ready
- Branch: `claude/zen-agnesi`
- Worktree: `.claude/worktrees/zen-agnesi`
- Owner: platform-infrastructure
- Depends On: `ADR 0224`
- Conflicts With: none

## Scope

- promote repo-intake as a first-class surface with its own subdomain
- align ops portal navigation with the new repo-intake entrypoint
- ensure generated nginx upstreams and platform service registry stay in sync

## Verification Plan

- `make generate-ops-portal`
- `make validate-generated-cross-cutting`
- `./scripts/validate_repo.sh generated-vars`

## Notes

- service will publish as `repo-intake.example.com` once applied in production

## Ownership Notes

- This document was backfilled on `2026-04-11` so shared registry validation can
  resolve the active workstream entry cleanly.
- Feature ownership remains with the declared workstream owner and branch.
