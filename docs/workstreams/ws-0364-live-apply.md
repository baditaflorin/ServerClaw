# Workstream ws-0364-live-apply: ADR 0364 Native Build Server Gate Execution Live Apply

- ADR: [ADR 0364](../adr/0364-native-build-server-gate-execution.md)
- Title: native build server gate execution
- Status: live_applied
- Branch: `codex/ws-0364-live-apply`
- Worktree: `.worktrees/ws-0364-live-apply`
- Owner: codex
- Latest Verified Base: `origin/main@022c93ec6`
- Depends On: `ADR 0082`, `ADR 0083`, `ADR 0087`, `ADR 0264`, `ADR 0266`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `workstreams/active/ws-0364-live-apply.yaml`, `docs/workstreams/ws-0364-live-apply.md`, `docs/adr/0364-native-build-server-gate-execution.md`, `docs/adr/.index.yaml`, `docs/runbooks/validation-gate.md`, `docs/runbooks/remote-build-gateway.md`, `config/build-server.json`, `config/validation-gate.json`, `inventory/build_server.yml`, `scripts/parallel_check.py`, `scripts/remote_exec.sh`, `scripts/live_apply_receipts.py`, `collections/ansible_collections/lv3/platform/playbooks/services/build-server-gate-tools.yml`, `receipts/live-applies/`

## Scope

- converge the ADR 0364 native gate toolchain onto `docker-build`
- verify `LV3_NATIVE_EXECUTION=1` on the remote build-server gate path end to end
- re-run repo automation and validation paths from the isolated worktree against the live build-server surface
- record durable live-apply receipt and evidence so a later merge can replay the verification chain quickly

## Non-Goals

- broad validation-gate redesign beyond fixes required to complete the live apply
- unrelated release bookkeeping on the workstream branch (`VERSION`, `changelog.md`, top-level `README.md`, `versions/stack.yaml`) unless exact-main integration on `main` later makes one of them mandatory

## Expected Repo Surfaces

- `workstreams/active/ws-0364-live-apply.yaml`
- `docs/workstreams/ws-0364-live-apply.md`
- `docs/adr/0364-native-build-server-gate-execution.md`
- `docs/runbooks/validation-gate.md`
- `docs/runbooks/remote-build-gateway.md`
- `docs/adr/.index.yaml`
- `receipts/live-applies/`

## Expected Live Surfaces

- `docker-build` (`10.10.10.30`) has the pinned native gate toolchain installed
- remote validation and pre-push gate runs execute natively on the build server without per-check Docker startup overhead
- `/opt/builds/gate-tool-versions.json` attests the installed gate tool versions

## Ownership Notes

- This branch owns the ADR 0364 live-apply tracking surfaces and receipt artifacts.
- Shared gate/runtime files stay merge-safe: only touch them if the live apply exposes a real gap that must be fixed to complete verification.

## Verification

- Live apply: `CANONICAL_TRUTH_SKIP_README=1 make apply-gate-tools env=production` succeeded with playbook recap `ok=7 changed=2 skipped=4`.
- Build server verification: `make check-build-server` succeeded; evidence in `receipts/live-applies/evidence/2026-04-12-ws-0364-check-build-server.txt`.
- Restic backup: `RESTIC_USE_FALLBACK_SCRIPT=1` restic trigger succeeded; receipts `receipts/restic-backups/20260412T072059Z.json` and refreshed `receipts/restic-snapshots-latest.json`.
- Remote validation: `make remote-validate` failed because build server runner images were unreachable and local Docker fallback timed out; evidence in `receipts/live-applies/evidence/2026-04-12-ws-0364-remote-validate.txt`.
- Pre-push gate: `make pre-push-gate` did not complete (remote gate hang). Rerun when registry/Docker runners are available.
- Live-apply receipt: `receipts/live-applies/2026-04-12-adr-0364-build-server-gate-tools-live-apply.json`.

## Merge Criteria

- live apply completed and evidenced
- ADR/runbook/workstream metadata updated with the verified live state
- repo automation and validation paths replayed from this worktree
- exact-main integration performed without rewriting unrelated concurrent work

## Notes For The Next Assistant

- The repo already contains the ADR 0364 implementation; this workstream exists to perform and document the live apply from latest `origin/main`.
- README generation is currently skipped via `CANONICAL_TRUTH_SKIP_README=1` because README lacks `platform-status` markers; fix template + regenerate before final mainline gate passes.
