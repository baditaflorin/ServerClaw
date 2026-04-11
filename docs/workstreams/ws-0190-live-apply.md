# Workstream ws-0190-live-apply: ADR 0190 Live Apply From Latest `origin/main`

- ADR: [ADR 0190](../adr/0190-synthetic-transaction-replay-for-capacity-and-recovery-validation.md)
- Title: live replay, verification, and evidence capture for synthetic transaction replay on restore targets
- Status: merged
- Implemented In Repo Version: 0.177.21
- Implemented On: 2026-03-28
- Branch: `codex/ws-0190-live-apply`
- Worktree: `.worktrees/ws-0190-live-apply`
- Owner: codex
- Depends On: `adr-0099-backup-restore-verification`, `adr-0105-capacity-model`, `adr-0171-controlled-fault-injection`, `adr-0181-off-host-witness-replication`
- Conflicts With: none
- Shared Surfaces: `scripts/restore_verification.py`, `scripts/synthetic_transaction_replay.py`, `config/synthetic-transaction-catalog.json`, `docs/runbooks/backup-restore-verification.md`, `docs/runbooks/synthetic-transaction-replay.md`, `receipts/restore-verifications/`, `receipts/live-applies/`

## Scope

- add a reusable synthetic replay harness for privacy-safe control-plane request sequences
- integrate the first governed replay into the restore-verification recovery path for restored `docker-runtime`
- validate the repo automation path and capture branch-local live-apply evidence without touching protected integration files

## Verification

- `python3 -m py_compile scripts/synthetic_transaction_replay.py scripts/restore_verification.py config/windmill/scripts/restore-verification.py` passed
- `uv run --with pytest --with pyyaml pytest tests/test_synthetic_transaction_replay.py tests/test_restore_verification.py tests/test_restore_verification_windmill.py -q` passed with `13 passed`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate` passed
- `make workflow-info WORKFLOW=restore-verification` rendered the updated workflow contract, including the ADR 0190 implementation refs and verification commands
- `make synthetic-transaction-replay SYNTHETIC_REPLAY_ARGS='--target restore-docker-runtime --dry-run'` validated the committed replay catalog through the Make target
- Initial full restore-verification replay from this worktree wrote `receipts/restore-verifications/2026-03-27-ws0190-attempt1.json`; it exposed two pre-existing restore-path issues outside ADR 0190 itself: the default 5-minute SSH wait was too short for restored guests, and `backup` currently has no PBS backup available
- Focused `docker-runtime` replays from this worktree wrote `receipts/restore-verifications/2026-03-27-ws0190-attempt2-qga.json` and the final `receipts/restore-verifications/2026-03-27.json`; the new Proxmox `qga` fallback allowed smoke tests and the ADR 0190 synthetic replay to execute end to end even without SSH
- The final focused replay still failed honestly on restored service health: Keycloak loopback discovery returned connection refused, NetBox and Windmill reset loopback connections, OpenBao remained sealed with HTTP `503`, and all four synthetic control-plane scenarios reported `0/12` successful requests on the restored target

## Outcome

- the repository now carries a reusable synthetic replay harness plus the first governed replay catalog for restored `docker-runtime`
- ADR 0099 restore verification now records synthetic replay success rate, latency distribution, validation-window context, and the guest execution mode used for the run
- the workstream also hardened the recovery path by adding a Proxmox guest-agent fallback when restored guests never expose an SSH banner through `vmbr20`
- live evidence is committed in `receipts/restore-verifications/2026-03-27-ws0190-attempt1.json`, `receipts/restore-verifications/2026-03-27-ws0190-attempt2-qga.json`, and `receipts/restore-verifications/2026-03-27.json`
- the repository-side implementation is now merged on `main` in release `0.177.21`, which assigned ADR 0190 its first `Implemented In Repo Version`

## Remaining For Platform Completion

- Platform-version advancement must still wait for a future replay where the restored `docker-runtime` services themselves become healthy enough for the smoke suite and synthetic replay to pass.
