# Workstream ws-0315-live-apply: Live Apply ADR 0315 From Latest `origin/main`

- ADR: [ADR 0315](../adr/0315-canonical-page-states-and-next-best-action-guidance-for-human-surfaces.md)
- Title: Live apply canonical page states and next-best-action guidance on the Windmill operator admin surface
- Status: live_applied
- Included In Repo Version: 0.177.140
- Branch-Local Receipt: `receipts/live-applies/2026-04-02-adr-0315-canonical-page-states-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0315-canonical-page-states-mainline-live-apply.json`
- Branch-Local Replay Source Commit: `cbb0c99f3f69c3ab2bb7658daf443c45df9ea49b`
- Branch-Local Replay Repo Version: `0.177.135`
- Branch-Local Replay Platform Version: `0.130.85`
- Live Applied In Platform Version: 0.130.88
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Exact-Main Replay Baseline: repo `0.177.139`, platform `0.130.87`
- Branch: `codex/ws-0315-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0315-live-apply`
- Owner: codex
- Depends On: `adr-0122-windmill-operator-access-admin`, `adr-0234-shared-human-app-shell-and-navigation-via-patternfly`, `adr-0236-server-state-and-mutation-feedback-via-tanstack-query`, `adr-0242-guided-human-onboarding-via-shepherd-tours`, `adr-0243-component-stories-accessibility-and-ui-contracts-via-storybook-playwright-and-axe-core`, `adr-0313-contextual-help-glossary-and-escalation-drawer`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `docs/workstreams/ws-0315-live-apply.md`, `docs/adr/0315-canonical-page-states-and-next-best-action-guidance-for-human-surfaces.md`, `docs/adr/.index.yaml`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/release-notes/README.md`, `docs/release-notes/0.177.140.md`, `docs/runbooks/windmill-operator-access-admin.md`, `docs/runbooks/validate-repository-automation.md`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/App.tsx`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/index.css`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package.json`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package-lock.json`, `config/windmill/scripts/gate-status.py`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`, `scripts/gate_status.py`, `tests/test_windmill_operator_admin_app.py`, `receipts/live-applies/2026-04-02-adr-0315-canonical-page-states-live-apply.json`, `receipts/live-applies/2026-04-02-adr-0315-canonical-page-states-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-ws-0315-*`, `receipts/sbom/host-docker-runtime-2026-04-02.cdx.json`

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
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/workstreams/ws-0315-live-apply.md`
- `docs/adr/0315-canonical-page-states-and-next-best-action-guidance-for-human-surfaces.md`
- `docs/adr/.index.yaml`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.140.md`
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
- `receipts/live-applies/2026-04-02-adr-0315-canonical-page-states-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-04-02-ws-0315-*`
- `receipts/sbom/host-docker-runtime-2026-04-02.cdx.json`

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
  with final recap `docker-runtime : ok=314 changed=48 unreachable=0 failed=0 skipped=99`, `postgres : ok=95 changed=6 unreachable=0 failed=0 skipped=28`, and `proxmox-host : ok=41 changed=4 unreachable=0 failed=0 skipped=16`.
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

## Exact-Main Verification

- `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-release-status.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-release-dry-run.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-release-write.txt`,
  and `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-release-write-r2.txt`
  capture the refreshed exact-main release cut on top of repository version
  `0.177.139`. The first write prepared repository version `0.177.140` before a
  post-write Outline sync `502`; the second write truthfully shows there were
  no remaining `## Unreleased` bullets because the release surfaces had already
  been cut.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-converge-windmill-r1.txt`
  captured the exact-main governed replay with final recap
  `docker-runtime : ok=327 changed=46 unreachable=0 failed=0 skipped=84`,
  `postgres : ok=93 changed=2 unreachable=0 failed=0 skipped=28`, and
  `proxmox-host : ok=41 changed=4 unreachable=0 failed=0 skipped=16`.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-targeted-tests-r1.txt`
  shows `29 passed in 4.51s` for
  `tests/test_validation_gate.py`,
  `tests/test_validation_gate_windmill.py`, and
  `tests/test_windmill_operator_admin_app.py` from the integrated release tree.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-raw-app-tsc-r1.txt`
  and `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-syntax-check-windmill-r1.txt`
  confirm the temporary raw-app checkout passed `npm ci --no-audit --no-fund`
  plus `npx tsc --noEmit`, and the Windmill playbook syntax lane passed from
  the exact-main worktree.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-remote-app-verify-r1.txt`
  confirms the browser route returned `200`, the deployed `/App.tsx` and
  `/index.css` digests still match the exact-main worktree byte-for-byte, and
  the live app continues to expose `Next best action`, `Help and recovery`,
  `Background Refresh`, `Validation Error`, `System Error`, `Unauthorized`,
  `Not Found`, `Latest Result`, `windmill-operator-access-admin`, and
  `validate-repository-automation`.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-generate-adr-index-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-canonical-truth-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-platform-manifest-r1.txt`,
  and `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-generate-diagrams-r1.txt`
  record the regenerated ADR index, canonical truth, platform manifest, and
  generated diagram surfaces after the release cut advanced the repository to
  `0.177.140` and the platform lineage to `0.130.88`.
- `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-agent-standards-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-workstream-surfaces-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-validate-data-models-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-live-apply-receipts-validate-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-validate-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-remote-validate-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-pre-push-gate-r1.txt`,
  and `receipts/live-applies/evidence/2026-04-02-ws-0315-mainline-git-diff-check-r1.txt`
  show the full repo automation and validation bundle passed from the exact-main
  tree, including the local validation suite, remote builder lane, primary
  branch pre-push gate, receipt/data-model validation, and `git diff --check`.

## Results

- ADR 0315 is now live on the governed Windmill operator admin app.
- The browser surface exposes one consistent state model with inline recovery
  guidance instead of page-local dead ends.
- The branch-local replay also repaired stale validation-wrapper drift inherited
  from the older worktree baseline, so the next exact-main replay starts from a
  cleaner branch than the first live apply did.
- The protected release surfaces now carry repository version `0.177.140`, and
  the exact-main replay has already re-verified the governed Windmill surface on
  the promoted platform lineage.
- The integrated tree also passed the full repo automation bundle, so the
  canonical receipt, release surfaces, and generated truth now agree on one
  merge-ready exact-main state.

## Mainline Note

The protected release and canonical-truth surfaces now reflect the exact-main
ADR 0315 replay on `codex/ws-0315-live-apply`, and the full validation bundle
has passed on that tree. No merge-only repo surfaces remain; the last step is
the final `origin/main` sync, merge, push, and worktree removal.
