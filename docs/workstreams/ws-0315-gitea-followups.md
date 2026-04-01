# Workstream ws-0315-gitea-followups: Gitea Release Bundles And Renovate PR Validation Follow-ups

- ADR: [ADR 0297](../adr/0297-renovate-bot-as-the-automated-stack-version-upgrade-proposer.md)
- Title: Resolve Gitea release bundle retention and Renovate PR validation checkout drift
- Status: live-applied
- Branch: `codex/ws-0315-gitea-followups`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0315-gitea-followups`
- Owner: codex
- Depends On: `ws-0297-main-merge`
- Conflicts With: none
- Shared Surfaces: `.gitea/workflows/validate.yml`, `.gitea/workflows/release-bundle.yml`, `scripts/release_bundle.py`, `docs/runbooks/configure-renovate.md`, `docs/runbooks/signed-release-bundles.md`, `docs/workstreams/ws-0315-gitea-followups.md`, `receipts/live-applies/2026-04-01-adr-0297-gitea-followups-live-apply.json`, `receipts/live-applies/evidence/2026-04-01-ws-0315-*`, `workstreams.yaml`

## Scope

- prune older Gitea `bundle-*` releases before publishing new assets to prevent attachment storage exhaustion
- harden the Gitea Actions checkout steps to wipe stale workspaces before pull-request validation runs
- re-run the failed release bundle and Renovate PR validation workflows after the fix lands

## Non-Goals

- altering the protected release cadence or stack version records outside the normal mainline integration step
- changing Renovate scope, schedules, or approval policies beyond the checkout and publish safeguards

## Expected Repo Surfaces

- `.gitea/workflows/validate.yml`
- `.gitea/workflows/release-bundle.yml`
- `scripts/release_bundle.py`
- `docs/runbooks/configure-renovate.md`
- `docs/runbooks/signed-release-bundles.md`
- `docs/workstreams/ws-0315-gitea-followups.md`
- `workstreams.yaml`
- `receipts/live-applies/2026-04-01-adr-0297-gitea-followups-live-apply.json`
- `receipts/live-applies/evidence/2026-04-01-ws-0315-*`

## Expected Live Surfaces

- private Gitea release bundle workflow prunes older `bundle-*` releases before uploading new assets
- Gitea pull-request validation runs start from a clean checkout on pre-existing Renovate PR branches

## Verification

- `release-bundle.yml` reruns succeeded on `codex/ws-0315-gitea-followups` (run IDs `225` and `227`).
- Renovate PR validations were re-triggered via `POST /pulls/{id}/update` for PRs `#6` and `#7` (runs `228` and `229`).
- PR validation failures now report repository data model mismatches (ClickHouse digest expectations) instead of incomplete checkout workspaces, confirming the cleanup fix landed.
