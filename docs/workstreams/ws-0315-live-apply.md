# Workstream ws-0315-live-apply: Live Apply ADR 0315 From Latest `origin/main`

- ADR: [ADR 0315](../adr/0315-canonical-page-states-and-next-best-action-guidance-for-human-surfaces.md)
- Title: Live apply canonical page states and next-best-action guidance on the Windmill operator admin surface
- Status: live_applied
- Included In Repo Version: not yet
- Branch-Local Receipt: `receipts/live-applies/2026-04-02-adr-0315-canonical-page-states-live-apply.json`
- Canonical Mainline Receipt: pending exact-main integration
- Branch-Local Replay Source Commit: `cbb0c99f3f69c3ab2bb7658daf443c45df9ea49b`
- Branch-Local Replay Repo Version: `0.177.135`
- Branch-Local Replay Platform Version: `0.130.85`
- Live Applied In Platform Version: 0.130.87
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Exact-Main Replay Baseline: repo `0.177.139`, platform `0.130.87`
- Branch: `codex/ws-0315-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0315-live-apply`
- Owner: codex
- Depends On: `adr-0122-windmill-operator-access-admin`, `adr-0234-shared-human-app-shell-and-navigation-via-patternfly`, `adr-0236-server-state-and-mutation-feedback-via-tanstack-query`, `adr-0242-guided-human-onboarding-via-shepherd-tours`, `adr-0243-component-stories-accessibility-and-ui-contracts-via-storybook-playwright-and-axe-core`, `adr-0313-contextual-help-glossary-and-escalation-drawer`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `build/platform-manifest.json`, `docs/workstreams/ws-0315-live-apply.md`, `docs/adr/0315-canonical-page-states-and-next-best-action-guidance-for-human-surfaces.md`, `docs/adr/.index.yaml`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/runbooks/windmill-operator-access-admin.md`, `docs/runbooks/validate-repository-automation.md`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/App.tsx`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/index.css`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package.json`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package-lock.json`, `config/windmill/scripts/gate-status.py`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`, `scripts/gate_status.py`, `tests/test_windmill_operator_admin_app.py`, `receipts/live-applies/2026-04-02-adr-0315-canonical-page-states-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-ws-0315-live-apply-*`, `receipts/sbom/host-docker-runtime-lv3-2026-04-02.cdx.json`

## Purpose

Implement ADR 0315 on the live Windmill `f/lv3/operator_access_admin` surface,
prove the page-state guidance survives the repo-managed raw-app sync path, and
leave exact evidence for the later mainline replay from the newest realistic
`origin/main` baseline.

## Scope

- add one explicit canonical page-state model to the governed operator admin raw
  app
- make loading, background refresh, empty, degraded, validation-error,
  system-error, unauthorized, not-found, and success outcomes explicit in the
  browser
- turn the latest-result panel into a handoff and recovery artifact instead of
  a dead-end log dump
- update the runbooks, validation guidance, and workstream metadata so another
  agent can merge safely without hidden context

## Non-Goals

- rewriting unrelated browser surfaces beyond the governed operator admin app
- updating protected release and canonical-truth surfaces on this workstream
  branch before the exact-main integration step
- treating the branch-local receipt as the final production truth after
  `origin/main` has already advanced beyond this worktree baseline

## Expected Repo Surfaces

- `workstreams.yaml`
- `build/platform-manifest.json`
- `docs/workstreams/ws-0315-live-apply.md`
- `docs/adr/0315-canonical-page-states-and-next-best-action-guidance-for-human-surfaces.md`
- `docs/adr/.index.yaml`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/runbooks/windmill-operator-access-admin.md`
- `docs/runbooks/validate-repository-automation.md`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/App.tsx`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/index.css`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package.json`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package-lock.json`
- `config/windmill/scripts/gate-status.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `scripts/gate_status.py`
- `tests/test_windmill_operator_admin_app.py`
- `receipts/live-applies/2026-04-02-adr-0315-canonical-page-states-live-apply.json`
- `receipts/live-applies/evidence/2026-04-02-ws-0315-live-apply-*`
- `receipts/sbom/host-docker-runtime-lv3-2026-04-02.cdx.json`

## Expected Live Surfaces

- Windmill workspace `lv3` serves `f/lv3/operator_access_admin` with one
  explicit canonical state inventory across the roster, inventory, notes, and
  latest-result surfaces
- every non-happy-path state says what happened, what the operator can do next,
  and where the owning runbook or validation guidance lives
- the deployed raw-app bundle matches the committed `App.tsx` and `index.css`
  bytes exactly after the governed replay

## Branch-Local Verification

- `receipts/live-applies/evidence/2026-04-02-ws-0315-live-apply-branch-tests.txt`
  shows `29 passed in 3.29s` for
  `tests/test_validation_gate.py`,
  `tests/test_validation_gate_windmill.py`, and
  `tests/test_windmill_operator_admin_app.py`.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-live-apply-raw-app-tsc.txt`
  confirms the temporary raw-app checkout passed `npm ci --no-audit --no-fund`
  and `npx tsc --noEmit`.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-live-apply-syntax-check-windmill.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0315-live-apply-agent-standards.txt`,
  and `receipts/live-applies/evidence/2026-04-02-ws-0315-live-apply-workstream-ownership.txt`
  confirm the Windmill syntax lane, ADR 0163-0168 gate, and branch ownership
  manifest all passed after the workstream surfaces were expanded to cover the
  gate-status wrappers, generated diagram, platform manifest, and SBOM receipt.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-live-apply-generate-diagrams.txt`
  refreshed the generated architecture diagram count after `pre-push-gate`
  exposed the stale `docs/diagrams/agent-coordination-map.excalidraw` artifact.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-live-apply-platform-manifest-check.txt`
  confirms the generated platform manifest now checks cleanly after the branch
  metadata changes.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-live-apply-converge-windmill-r1.txt`
  and `...-r2.txt` truthfully preserve the first two replay failures caused by
  stale branch-baseline copies of `config/windmill/scripts/gate-status.py` and
  `scripts/gate_status.py`; `...-r3.txt` captured the repaired governed replay
  with final recap `docker-runtime-lv3 : ok=314 changed=48 unreachable=0 failed=0 skipped=99`, `postgres-lv3 : ok=95 changed=6 unreachable=0 failed=0 skipped=28`, and `proxmox_florin : ok=41 changed=4 unreachable=0 failed=0 skipped=16`.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-live-apply-remote-app-verify.txt`
  confirms the authenticated browser route returned `200`, the deployed
  `/App.tsx` and `/index.css` digests match the local worktree exactly, and the
  live raw app contains `Next best action`, `Help and recovery`,
  `Background Refresh`, `Validation Error`, `System Error`, `Unauthorized`,
  `Not Found`, `Latest Result`, `windmill-operator-access-admin`, and
  `validate-repository-automation`.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-live-apply-pre-push-gate-r2.txt`
  preserves the full branch-local repo automation rehearsal after the ownership
  and dependency-graph repairs. Every remote lane passed except two generated
  truth surfaces: `generated-docs` still wants the protected `README.md`
  canonical-truth write, and `schema-validation` was still observing the older
  `build/platform-manifest.json` snapshot at the time that replay started.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-live-apply-canonical-truth-check.txt`
  now shows the only remaining branch-local generated-docs blocker is the
  protected `README.md` update that belongs to the exact-main integration step.

## Results

- ADR 0315 is now live on the governed Windmill operator admin app.
- The browser surface exposes one consistent state model with inline recovery
  guidance instead of page-local dead ends.
- The branch-local replay also repaired stale validation-wrapper drift inherited
  from the older worktree baseline, so the next exact-main replay starts from a
  cleaner branch than the first live apply did.

## Mainline Note

The exact-main merge still has to:

- rebase onto the latest realistic `origin/main` baseline
- update the protected release and canonical-truth surfaces
  `README.md`, `VERSION`, `changelog.md`, and `versions/stack.yaml`
- create the canonical mainline ADR 0315 receipt
- rerun `make validate`, `make remote-validate`, `make pre-push-gate`, and the
  exact-main live replay from that integrated tree

This branch-local receipt is therefore merge-safe evidence, not the final
canonical production record.
