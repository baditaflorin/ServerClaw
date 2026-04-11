# Workstream ws-0304-live-apply: Live Apply ADR 0304 From Latest `origin/main`

- ADR: [ADR 0304](../adr/0304-atlas-for-declarative-database-schema-migration-versioning-and-pre-migration-linting.md)
- Title: Atlas schema validation, snapshot refresh, and Windmill drift detection latest-main replay
- Status: merged
- Latest Realistic Live Baseline Commit: `e28f1e51729a23c5a3d9b384ec285571a50cfa58`
- Latest Realistic Live Baseline Repo Version: `0.177.142`
- Latest Realistic Live Baseline Platform Version: `0.130.90`
- Final Integrated `origin/main` Head: `d10174f9f04c6b2e72581e6a262d5c96d0d07d0f`
- Final Integrated `origin/main` Repo Version: `0.177.149`
- Final Integrated `origin/main` Platform Version: `0.130.93`
- Included In Repo Version: `0.177.150`
- Live Applied In Platform Version: `0.130.90`
- Implemented On: `2026-04-02`
- Branch: `codex/ws-0304-mainline`
- Worktree: `.worktrees/ws-0304-mainline`
- Owner: codex
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0304-atlas-mainline-live-apply.json`

## Outcome

- Rebased the ADR 0304 live-apply branch onto the latest realistic live baseline `e28f1e51` (repo `0.177.142`, platform `0.130.90`) for the replay work, then carried the final repository closeout on top of `origin/main` head `d10174f9` (repo `0.177.149`, platform `0.130.93`) after the exact-main GlitchTip integration release landed during verification.
- Replayed the dependency chain end to end from the current codebase state: `make converge-step-ca env=production` completed from the realistic live baseline, while `make converge-openbao env=production` and `make converge-windmill env=production` completed after the mainline rebase, confirming that the later integration releases did not change the Atlas, OpenBao, or Windmill live paths.
- The replay surfaced three latest-main stability gaps and fixed them in-repo before the final merge: default Docker bridge-chain recovery in `linux_guest_firewall`, retry guards around PostgreSQL pgaudit grant steps, and a localhost Windmill API wait before repo-managed script sync while retaining the stricter runtime env contract gate for consumer startup and recreation.
- Refreshed Atlas snapshots after the live replay and re-verified both the repo-side `atlas-drift-check` path and the seeded `f/lv3/atlas_drift_check` Windmill job clean with `drift_count: 0` and no published notifications across the 20 cataloged PostgreSQL databases.
- Re-ran repository automation and governed validation on the rebased mainline closeout tree: the full pre-push sweep on `0.177.149` failed only because `docs/diagrams/agent-coordination-map.excalidraw` was stale, and the exact remaining governed closeout checks passed after regenerating the shared diagram and cutting the final `0.177.150` release surfaces.

## Verification

- `make converge-step-ca env=production`
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-converge-step-ca-r6-0.177.142.txt`
  Result: the latest realistic live-baseline Step-CA replay passed with final recap `docker-runtime : ok=124 changed=1 failed=0`, `proxmox-host : ok=54 changed=4 failed=0`, and no failed hosts across the remaining guests.
- `make converge-openbao env=production`
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-converge-openbao-r4-0.177.142.txt`
  Result: the integrated-main OpenBao replay passed with final recap `docker-runtime : ok=381 changed=8 failed=0` and `postgres : ok=75 changed=1 failed=0`.
- `make converge-windmill env=production`
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-converge-windmill-r7-0.177.142.txt`
  Result: the integrated-main Windmill replay finished cleanly with final recap `docker-runtime : ok=363 changed=48 failed=0`, `postgres : ok=92 changed=1 failed=0`, and `proxmox-host : ok=41 changed=4 failed=0`.
- Repo Atlas automation path
  Evidence:
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-refresh-snapshots-r5-0.177.142.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-validate-r5-0.177.142.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-lint-r4-0.177.142.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-drift-check-r5-0.177.142.txt`
  Result: `atlas-refresh-snapshots`, `atlas-validate`, `atlas-lint`, and the repo-side `atlas-drift-check` all passed from the rebased tree with `drift_count: 0`, no drift receipts, and no NATS or ntfy notifications.
- Seeded Windmill Atlas drift job
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-drift-check-seeded-r5-0.177.142.txt`
  Result: the seeded `f/lv3/atlas_drift_check` job returned `returncode: 0`, `report.status: clean`, `drift_count: 0`, and no published notifications across the 20 cataloged PostgreSQL databases.
- Targeted latest-main regression slice
  Evidence: `receipts/live-applies/evidence/2026-04-03-ws-0304-mainline-targeted-pytest-r7-0.177.150.txt`
  Result: the final protected-surface closeout tree re-passed the targeted latest-main regression slice with `22 passed`, covering the validation gate, diagram closeout path, and the earlier firewall, PostgreSQL, Windmill runtime, OpenBao runtime helper, and compose-runtime regression surfaces.
- Governed remote validation automation lane
  Evidence: `receipts/live-applies/evidence/2026-04-03-ws-0304-mainline-remote-validate-r3-0.177.148.txt`
  Result: the exact configured local fallback for `make remote-validate` passed on the rebased tree, including `ansible-syntax`, `schema-validation`, `atlas-lint`, `policy-validation`, `iac-policy-scan`, `alert-rule-validation`, `type-check`, `dependency-graph`, `agent-standards`, and `workstream-surfaces`.
- Governed repository validation and closeout gates
  Evidence:
  - `receipts/live-applies/evidence/2026-04-03-ws-0304-mainline-pre-push-gate-r5-0.177.149.txt`
  - `receipts/live-applies/evidence/2026-04-03-ws-0304-mainline-closeout-gates-r1-0.177.149.txt`
  - `receipts/live-applies/evidence/2026-04-03-ws-0304-mainline-closeout-gates-r2-0.177.150.txt`
  Result: the full governed pre-push sweep on the rebased `0.177.149` tree passed every lane except `generated-docs` and `dependency-graph`, both blocked only by the stale generated `agent-coordination-map.excalidraw`; after regenerating that shared diagram and cutting the `0.177.150` release surfaces, the exact remaining closeout checks re-passed on the final tree.

## Merge Notes

- This workstream became the final integration step on top of `d10174f9`, so the protected release and canonical-truth files were updated here for release `0.177.150`: `VERSION`, `RELEASE.md`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/0.177.150.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `README.md`, `workstreams.yaml`, and the ADR/workstream state while preserving the already-published `0.177.149` GlitchTip release surfaces from `origin/main`.
- The combined proof set is authoritative because the later exact-main GlitchTip release changed shared release, docs, and canonical-truth surfaces but did not change the Atlas, OpenBao, or Windmill live-apply automation path; the Step-CA replay from `e28f1e51` and the later OpenBao, Windmill, Atlas, and rebased validation replays all remained consistent.
- The canonical receipt id reserved for `versions/stack.yaml` and `workstreams.yaml` is `2026-04-02-adr-0304-atlas-mainline-live-apply`.
