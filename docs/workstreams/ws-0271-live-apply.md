# Workstream WS-0271: Backup Coverage Assertion Ledger Live Apply

- ADR: [ADR 0271](../adr/0271-backup-coverage-assertion-ledger-and-backup-of-backup-policy.md)
- Title: Backup coverage assertion ledger and backup-of-backup policy live apply
- Status: live_applied
- Branch: `codex/ws-0271-backup-coverage-ledger`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0271-backup-coverage-ledger`
- Owner: codex
- Depends On: `adr-0029-dedicated-backup-vm`, `adr-0099-backup-restore-verification`, `adr-0100-disaster-recovery-playbook`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0271`, `docs/runbooks/backup-coverage-ledger.md`, `docs/runbooks/configure-backup-vm.md`, `docs/runbooks/disaster-recovery.md`, `scripts/backup_coverage_ledger.py`, `scripts/generate_dr_report.py`, `config/windmill/scripts/backup-coverage-ledger.py`, `receipts/backup-coverage/`, `receipts/live-applies/`

## Scope

- turn ADR 0271 into a governed evidence surface instead of a narrative policy
- extend the nightly Proxmox backup job so `coolify-lv3` on VM `170` is part of the protected PBS set
- make the DR report consume the latest backup coverage receipt and show uncovered assets explicitly
- document the remaining off-site gap for `backup-lv3` without pretending it is already solved live

## Non-Goals

- provisioning `lv3-backup-offsite` or a second-site copy during this workstream
- claiming full-host off-site disaster recovery before the off-site storage path exists
- changing protected integration files on the branch before the final merge step

## Expected Repo Surfaces

- `scripts/backup_coverage_ledger.py`
- `config/windmill/scripts/backup-coverage-ledger.py`
- `scripts/generate_dr_report.py`
- `docs/runbooks/backup-coverage-ledger.md`
- `docs/runbooks/configure-backup-vm.md`
- `docs/runbooks/disaster-recovery.md`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `Makefile`
- `workstreams.yaml`

## Expected Live Surfaces

- Proxmox backup job `backup-lv3-nightly` now governs VMIDs `110,120,130,140,150,170`
- PBS storage `lv3-backup-pbs` now holds a fresh artifact for VM `170`
- DR readiness surfaces now call out `backup-lv3` as the one remaining uncovered governed asset until off-site storage exists

## Verification

- `make configure-backup-vm` completed successfully from this worktree with `backup-lv3 : ok=46 changed=2 unreachable=0 failed=0 skipped=11 rescued=0 ignored=0` and `proxmox_florin : ok=35 changed=7 unreachable=0 failed=0 skipped=30 rescued=0 ignored=0`.
- `sudo pvesh get /cluster/backup/backup-lv3-nightly --output-format json-pretty` on `proxmox_florin` returned `vmid : "110,120,130,140,150,170"`.
- `sudo vzdump 170 --storage lv3-backup-pbs --mode snapshot --compress zstd --notification-mode notification-system` completed successfully on 2026-03-29 and produced `lv3-backup-pbs:backup/vm/170/2026-03-29T11:22:40Z`.
- `make backup-coverage-ledger` wrote `receipts/backup-coverage/20260329T113418Z.json` after the latest-`origin/main` replay and reported `Protected: 6  Degraded: 0  Uncovered: 1  Governed assets: 7`, with only `backup-lv3` uncovered.
- `python3 config/windmill/scripts/backup-coverage-ledger.py --repo-path /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0271-backup-coverage-ledger` returned `status: ok` and the same `6/7 protected` summary after adding CLI flag support for local repo-path testing.
- `make dr-status` reported `Backup coverage ledger warn 6/7 protected; uncovered backup-lv3`, which is the intended honest state until `lv3-backup-offsite` exists.
- `make preflight WORKFLOW=backup-coverage-ledger`, `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`, and the focused pytest slice for `tests/test_backup_coverage_ledger.py`, `tests/test_backup_coverage_ledger_windmill.py`, and `tests/test_disaster_recovery.py` all passed.
- The branch records the canonical live apply receipt at `receipts/live-applies/2026-03-29-adr-0271-backup-coverage-ledger-live-apply.json`, including the latest-`origin/main` replay commit and the explicit remaining off-site gap.

## Mainline Integration

- This workstream has been live-applied on the platform and replayed from the exact latest `origin/main` branch tip, but the branch still needs the final merge-to-main release surfaces updated on `main`.
- The remaining live gap is explicit and intentional: `backup-lv3` stays `uncovered` until `lv3-backup-offsite` exists and receives fresh VM `160` evidence.
- When the branch is merged, update ADR 0271 implementation metadata, release truth, and the final live-apply receipt without hiding that off-site coverage is still pending.

## Notes For The Next Assistant

- If you need to re-verify immediately, rerun `make backup-coverage-ledger` before `make dr-status`; the DR report reads the latest receipt rather than querying Proxmox directly.
- The Windmill wrapper now supports `--repo-path`, `--strict`, and `--no-write-receipt`, which makes local end-to-end verification consistent with other wrappers in `config/windmill/scripts/`.
