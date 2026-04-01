# Workstream ws-0304-live-apply: Live Apply ADR 0304 From Latest `origin/main`

- ADR: [ADR 0304](../adr/0304-atlas-for-declarative-database-schema-migration-versioning-and-pre-migration-linting.md)
- Title: Atlas schema validation, snapshot refresh, and Windmill drift detection exact-main replay
- Status: live_applied
- Latest `origin/main`: `b7dde631d290474de3200886846217e688e0c16e`
- Latest `origin/main` Repo Version: `0.177.134`
- Latest `origin/main` Platform Version: `0.130.84`
- Included In Repo Version: `0.177.135`
- Live Applied In Platform Version: `0.130.85`
- Implemented On: `2026-04-01`
- Branch: `codex/ws-0304-mainline`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0304-mainline`
- Owner: codex
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-01-adr-0304-atlas-mainline-live-apply.json`

## Outcome

- Rebased the ADR 0304 live-apply branch onto the latest realistic
  `origin/main` baseline (`b7dde631`) before the final replay and kept the
  protected integration files untouched until the exact-main release step.
- Verified the OpenBao runtime still delivers the Atlas AppRole and ntfy
  secrets into the isolated Windmill checkout through the repo-managed seeded
  job secret path.
- Restored the governed Windmill validation-gate contract by teaching
  `config/windmill/scripts/gate-status.py` to rebuild `gate_status.waiver_summary`
  when the latest-main `scripts/gate_status.py` payload omits it.
- Fixed a release-automation gap exposed by the final release refresh by
  classifying `platform-db-subjects` in `config/api-publication.json`.

## Verification

- `make converge-openbao env=production`
  Evidence: `receipts/live-applies/evidence/2026-04-01-ws-0304-mainline-converge-openbao-r1-0.177.134.txt`
  Result: `docker-runtime-lv3 : ok=379 changed=8 failed=0`; `postgres-lv3 : ok=73 changed=1 failed=0`
- `make converge-windmill env=production`
  Evidence:
  - `receipts/live-applies/evidence/2026-04-01-ws-0304-mainline-converge-windmill-r1-0.177.134.txt`
  - `receipts/live-applies/evidence/2026-04-01-ws-0304-mainline-converge-windmill-r2-0.177.134.txt`
  Result: the first replay exposed the missing `waiver_summary` contract on the
  latest-main wrapper; the second replay passed with final recap
  `docker-runtime-lv3 : ok=353 changed=46 failed=0`,
  `postgres-lv3 : ok=91 changed=2 failed=0`,
  `proxmox_florin : ok=41 changed=4 failed=0`
- Seeded Windmill Atlas drift job
  Evidence: `receipts/live-applies/evidence/2026-04-01-ws-0304-mainline-atlas-drift-check-seeded-r1-0.177.134.txt`
  Result: `status: ok`, `report.status: clean`, `drift_count: 0`
- Repo Atlas automation path
  Evidence:
  - `receipts/live-applies/evidence/2026-04-01-ws-0304-mainline-atlas-validate-r1-0.177.134.txt`
  - `receipts/live-applies/evidence/2026-04-01-ws-0304-mainline-atlas-lint-r1-0.177.134.txt`
  - `receipts/live-applies/evidence/2026-04-01-ws-0304-mainline-atlas-refresh-snapshots-r1-0.177.134.txt`
  - `receipts/live-applies/evidence/2026-04-01-ws-0304-mainline-atlas-validate-r2-0.177.134.txt`
  - `receipts/live-applies/evidence/2026-04-01-ws-0304-mainline-atlas-drift-check-r1-0.177.134.txt`
  Result: validate, lint, snapshot refresh, re-validate, and repo-side drift
  check all passed with clean drift output
- Focused and targeted repository validation
  Evidence:
  - `receipts/live-applies/evidence/2026-04-01-ws-0304-mainline-gate-status-focused-tests-r1-0.177.134.txt`
  - `receipts/live-applies/evidence/2026-04-01-ws-0304-mainline-targeted-pytest-r1-0.177.134.txt`
  - `receipts/live-applies/evidence/2026-04-01-ws-0304-mainline-targeted-pytest-r2-0.177.134.txt`
  - `receipts/live-applies/evidence/2026-04-01-ws-0304-mainline-py-compile-r1-0.177.134.txt`
  Result: focused Windmill suite passed (`72 passed`), the first broader slice
  exposed two stale OpenBao helper assertions, and the second broader slice
  passed (`167 passed`)

## Merge Notes

- This workstream became the exact mainline integration step, so the protected
  release and canonical-truth files were updated here after live verification:
  `VERSION`, `RELEASE.md`, `changelog.md`, `docs/release-notes/README.md`,
  `docs/release-notes/0.177.135.md`, `versions/stack.yaml`,
  `build/platform-manifest.json`, `workstreams.yaml`, and the ADR/runbook state.
- The canonical receipt id reserved for `versions/stack.yaml` and
  `workstreams.yaml` is `2026-04-01-adr-0304-atlas-mainline-live-apply`.
