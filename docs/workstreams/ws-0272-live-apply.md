# Workstream ws-0272-live-apply: ADR 0272 Live Apply From Latest `origin/main`

- ADR: [ADR 0272](../adr/0272-restore-readiness-ladders-and-stateful-warm-up-verification-profiles.md)
- Title: live apply of restore-readiness ladders and governed warm-up profiles for restore verification
- Status: in_progress
- Branch: `codex/adr-0272-restore-readiness-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/adr-0272-restore-readiness`
- Owner: codex
- Depends On: `adr-0099-backup-restore-verification`, `adr-0190-synthetic-transaction-replay`, `adr-0246-startup-readiness-liveness-and-degraded-state-semantics`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0272-live-apply.md`, `docs/adr/0272-restore-readiness-ladders-and-stateful-warm-up-verification-profiles.md`, `docs/adr/.index.yaml`, `docs/runbooks/backup-restore-verification.md`, `.config-locations.yaml`, `config/restore-readiness-profiles.json`, `docs/schema/restore-readiness-profiles.schema.json`, `scripts/restore_verification.py`, `scripts/validate_repository_data_models.py`, `config/workflow-catalog.json`, `tests/test_restore_verification.py`, `receipts/restore-verifications/`, `receipts/live-applies/`

## Scope

- add a governed restore-readiness profile catalog for the protected restore targets
- teach `scripts/restore_verification.py` to record readiness ladders, warm-up attempts, and the highest completed recovery stage
- verify the repository automation and the live restore path end to end from a separate worktree

## Verification

- in progress

## Outcome

- in progress

## Remaining For Platform Completion

- in progress
