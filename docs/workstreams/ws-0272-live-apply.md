# Workstream ws-0272-live-apply: ADR 0272 Live Apply From Latest `origin/main`

- ADR: [ADR 0272](../adr/0272-restore-readiness-ladders-and-stateful-warm-up-verification-profiles.md)
- Title: live apply of restore-readiness ladders and governed warm-up profiles for restore verification
- Status: live_applied
- Implemented In Repo Version: 0.177.75
- Live Applied In Platform Version: 0.130.51
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
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

- `git fetch origin --prune` confirmed the latest published `origin/main` had
  advanced to commit `767951428ffb1d281eed273c15333f93d18515a3`, so the final
  ADR 0272 integration was replayed from a fresh worktree based on that head.
- `uv run --with pyyaml python scripts/restore_verification.py --selection-strategy latest --ssh-timeout-seconds 900 --triggered-by ws-0272-mainline-r2 --actor-id ws-0272-mainline-r2 --print-report-json`
  completed from the refreshed latest-main worktree, exited non-zero because
  the live restore health is still degraded, and wrote the canonical exact-main
  receipt `receipts/restore-verifications/2026-03-29.json`.
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 'sudo qm list | egrep "VMID| 900 | 901 | 902 " || true'`
  returned only the table header after the replay, confirming the temporary
  restore VMIDs were cleaned up.
- `python3 -m py_compile scripts/restore_verification.py scripts/synthetic_transaction_replay.py scripts/smoke_tests/postgres_smoke.py scripts/smoke_tests/docker_runtime_smoke.py scripts/smoke_tests/backup_vm_smoke.py config/windmill/scripts/restore-verification.py`
  passed.
- `uv run --with pytest --with pyyaml pytest tests/test_restore_verification.py tests/test_restore_verification_windmill.py tests/test_synthetic_transaction_replay.py -q`
  passed with `17 passed`.
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
  passed.
- `./scripts/validate_repo.sh agent-standards` passed after the conflicted
  `workstreams.yaml` block was repaired.
- `./scripts/validate_repo.sh generated-docs`, `uv run --with pyyaml python scripts/canonical_truth.py --check`, `uvx --from pyyaml python scripts/generate_status_docs.py --check`, `uv run --with pyyaml python scripts/generate_diagrams.py --check`, `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`, `uv run --with pyyaml --with jsonschema python scripts/live_apply_receipts.py --validate`, and `git diff --check` all passed on the final integrated tree.

## Outcome

- release `0.177.75` carries ADR 0272 onto `main`, and the exact-main replay
  establishes platform version `0.130.51` for the governed restore-readiness
  ladder and warm-up-profile semantics.
- `scripts/restore_verification.py` now records the highest completed
  readiness-ladder stage, every warm-up attempt, the active readiness profile,
  and whether synthetic replay was eligible instead of collapsing each target
  into a single binary smoke-test result.
- the latest exact-main restore receipt shows the new semantics working as
  intended on live infrastructure: `postgres-lv3`, `docker-runtime-lv3`, and
  `backup-lv3` all stop at `restore_completed`, with the failure cause now
  preserved explicitly per target instead of being hidden behind a generic
  restore-verification failure.
- `receipts/live-applies/2026-03-29-adr-0272-restore-readiness-mainline-live-apply.json`
  is the canonical integrated proof for this mainline live apply.

## Remaining For Platform Completion

- repair the `postgres-lv3` PBS restore failure so the workflow can progress
  beyond the `restore_completed` stage on the primary stateful database path
- repair the `docker-runtime-lv3` `pbs-restore` failure, which now prevents the
  control-plane recovery path from reaching any later readiness stage on the
  newest mainline baseline
- restore eligible PBS snapshot coverage for `backup-lv3`, which currently has
  no backup artifact available for the governed selection window
