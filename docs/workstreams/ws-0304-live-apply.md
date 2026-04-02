# Workstream ws-0304-live-apply: Live Apply ADR 0304 From Latest `origin/main`

- ADR: [ADR 0304](../adr/0304-atlas-for-declarative-database-schema-migration-versioning-and-pre-migration-linting.md)
- Title: Atlas schema validation, snapshot refresh, and Windmill drift detection exact-main replay
- Status: live_applied
- Exact-main Baseline Commit: `cf255eeca51d0b6c1e65ce19a5924d55ed2ed7a4`
- Exact-main Baseline Repo Version: `0.177.140`
- Exact-main Baseline Platform Version: `0.130.88`
- Included In Repo Version: `0.177.141`
- Live Applied In Platform Version: `0.130.89`
- Implemented On: `2026-04-02`
- Branch: `codex/ws-0304-mainline`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0304-mainline`
- Owner: codex
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0304-atlas-mainline-live-apply.json`

## Outcome

- Rebased the ADR 0304 live-apply branch onto the latest realistic
  `origin/main` baseline (`cf255eec`) before the final replay and kept the
  protected integration files untouched until the exact-main release step.
- Replayed the current-main dependency chain end to end:
  `make converge-step-ca env=production`, `make converge-openbao env=production`,
  and `make converge-windmill env=production` all completed successfully from
  the rebased tree before the final release surfaces were cut.
- The first current-main `make atlas-refresh-snapshots` attempt timed out on
  `<urlopen error timed out>` before the live replay; rerunning the same Atlas
  controller path after the step-ca/OpenBao/Windmill re-converge passed
  cleanly from the same tree.
- The current-main Windmill replay exercised the built-in Docker bridge-chain
  rescue path when `docker-runtime-lv3` temporarily lost the `nat DOCKER`
  chain during guest-firewall evaluation; the playbook recovered, continued,
  and finished with `failed=0`.
- Verified the seeded Windmill `f/lv3/atlas_drift_check` path end to end after
  the current-main replay: the job returned `status: ok`, `report.status: clean`,
  `drift_count: 0`, and no published notifications from the repo-backed worker
  checkout.

## Verification

- `make converge-step-ca env=production`
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-converge-step-ca-r1-0.177.140.txt`
  Result: the current-main step-ca replay passed with final recap
  `docker-runtime-lv3 : ok=145 changed=4 failed=0`,
  `proxmox_florin : ok=54 changed=4 failed=0`, and no failed hosts.
- `make converge-openbao env=production`
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-converge-openbao-r1-0.177.140.txt`
  Result: the current-main OpenBao replay passed with final recap
  `docker-runtime-lv3 : ok=385 changed=8 failed=0` and
  `postgres-lv3 : ok=75 changed=1 failed=0`.
- `make converge-windmill env=production`
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-converge-windmill-r1-0.177.140.txt`
  Result: the current-main Windmill replay hit a transient missing `nat DOCKER`
  chain on `docker-runtime-lv3`, exercised the built-in Docker recovery path,
  and still finished cleanly with final recap
  `docker-runtime-lv3 : ok=384 changed=53 failed=0 rescued=1`,
  `postgres-lv3 : ok=95 changed=6 failed=0`,
  `proxmox_florin : ok=41 changed=4 failed=0`.
- Seeded Windmill Atlas drift job
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-drift-check-seeded-r1-0.177.140.txt`
  Result: `status: ok`, `report.status: clean`, `drift_count: 0`, and no
  published notifications across the 20 cataloged PostgreSQL databases.
- Repo Atlas automation path
  Evidence:
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-validate-r1-0.177.140.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-lint-r1-0.177.140.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-refresh-snapshots-r1-0.177.140.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-refresh-snapshots-r2-0.177.140.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-validate-r2-0.177.140.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-drift-check-r2-0.177.140.txt`
  Result: `atlas-validate` and `atlas-lint` passed immediately from the rebased
  tree, the first `atlas-refresh-snapshots` attempt timed out before the live
  replay, and the post-replay `atlas-refresh-snapshots`, re-validate, and
  repo-side drift check all passed with `drift_count: 0`.
- Targeted repository validation and closeout gates
  Evidence:
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-targeted-pytest-r1-0.177.140.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-validation-runner-contracts-validate-r2-0.177.141.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-agent-standards-r2-0.177.141.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-diff-check-r1-0.177.141.txt`
  Result: the targeted repository slice passed (`68 passed`), the final
  validation-runner contracts validated cleanly, `./scripts/validate_repo.sh
  agent-standards` passed from the release-cut tree, and `git diff --check`
  reported no whitespace or conflict-marker defects before the mainline push.

## Merge Notes

- This workstream became the exact mainline integration step, so the protected
  release and canonical-truth files were updated here after live verification:
  `VERSION`, `RELEASE.md`, `changelog.md`, `docs/release-notes/README.md`,
  `docs/release-notes/0.177.141.md`, `versions/stack.yaml`,
  `build/platform-manifest.json`, `README.md`, `workstreams.yaml`, and the
  ADR/runbook state.
- The canonical receipt id reserved for `versions/stack.yaml` and
  `workstreams.yaml` is `2026-04-02-adr-0304-atlas-mainline-live-apply`.
