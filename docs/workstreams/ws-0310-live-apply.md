# Workstream ws-0310-live-apply: Live Apply ADR 0310 From Latest `origin/main`

- ADR: [ADR 0310](../adr/0310-first-run-activation-checklists-and-progressive-capability-reveal.md)
- Title: Implement the first-run activation checklist and progressive capability reveal inside the interactive ops portal, then verify the live path end to end
- Status: live_applied
- Included In Repo Version: 0.177.144
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0310-activation-checklist-mainline-live-apply.json`
- Exact-Main Replay Source Commit: `4125edb25791a0e025dfc13976fe847282231712`
- Live Applied In Platform Version: 0.130.91
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Exact-Main Replay Baseline: repo `0.177.143`, platform `0.130.90`
- Branch: `codex/ws-0310-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0310-live-apply`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal-runtime-contract`, `adr-0108-operator-onboarding-and-offboarding`, `adr-0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher`, `adr-0242-guided-human-onboarding-via-shepherd-tours`, `adr-0308-journey-aware-entry-routing-and-saved-home-selection`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `inventory/group_vars/platform.yml`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/workstreams/ws-0310-live-apply.md`, `docs/adr/0310-first-run-activation-checklists-and-progressive-capability-reveal.md`, `docs/adr/.index.yaml`, `docs/runbooks/platform-operations-portal.md`, `docs/runbooks/operator-onboarding.md`, `docs/runbooks/windmill-operator-access-admin.md`, `Makefile`, `playbooks/ops-portal.yml`, `.config-locations.yaml`, `config/activation-checklist.json`, `docs/schema/activation-checklist.schema.json`, `scripts/validate_repository_data_models.py`, `scripts/ops_portal/app.py`, `scripts/ops_portal/static/portal.css`, `scripts/ops_portal/templates/base.html`, `scripts/ops_portal/templates/index.html`, `scripts/ops_portal/templates/partials/activation.html`, `scripts/ops_portal/templates/partials/launcher.html`, `scripts/ops_portal/templates/partials/overview.html`, `scripts/ops_portal/templates/partials/runbooks.html`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`, `tests/test_interactive_ops_portal.py`, `tests/test_ops_portal_playbook.py`, `tests/test_ops_portal_runtime_role.py`, `receipts/live-applies/2026-04-02-adr-0310-activation-checklist-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-ws-0310-*`, `receipts/restic-backups/20260402T122554Z.json`, `receipts/restic-backups/20260402T124641Z.json`, `receipts/restic-snapshots-latest.json`, `receipts/sbom/host-docker-runtime-lv3-2026-04-02.cdx.json`

## Purpose

Land ADR 0310 on the existing browser-first operator path without creating a
separate onboarding product: add a repo-managed activation checklist catalog,
persist checklist progress in the interactive ops portal session, and keep
advanced launcher destinations plus mutating controls hidden or disabled until
the required first-run stages are complete or explicitly revealed.

## Scope

- add the catalog and schema for first-run activation stages, links, and
  progressive reveal policy
- render the activation checklist directly inside `ops.lv3.org`
- gate admin launcher entries, mutating service actions, and mutating runbooks
  on the same server-side activation state
- sync and verify the new checklist partial through the managed ops-portal
  runtime role
- document how operator provisioning, Windmill access administration, and the
  live ops portal fit together in the first-run flow

## Expected Repo Surfaces

- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.144.md`
- `versions/stack.yaml`
- `inventory/group_vars/platform.yml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/0310-first-run-activation-checklists-and-progressive-capability-reveal.md`
- `docs/workstreams/ws-0310-live-apply.md`
- `docs/runbooks/platform-operations-portal.md`
- `docs/runbooks/operator-onboarding.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `Makefile`
- `playbooks/ops-portal.yml`
- `.config-locations.yaml`
- `config/activation-checklist.json`
- `docs/schema/activation-checklist.schema.json`
- `scripts/validate_repository_data_models.py`
- `scripts/ops_portal/app.py`
- `scripts/ops_portal/static/portal.css`
- `scripts/ops_portal/templates/base.html`
- `scripts/ops_portal/templates/index.html`
- `scripts/ops_portal/templates/partials/activation.html`
- `scripts/ops_portal/templates/partials/launcher.html`
- `scripts/ops_portal/templates/partials/overview.html`
- `scripts/ops_portal/templates/partials/runbooks.html`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`
- `tests/test_interactive_ops_portal.py`
- `tests/test_ops_portal_playbook.py`
- `tests/test_ops_portal_runtime_role.py`
- `receipts/live-applies/2026-04-02-adr-0310-activation-checklist-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-04-02-ws-0310-*`
- `receipts/restic-backups/20260402T122554Z.json`
- `receipts/restic-backups/20260402T124641Z.json`
- `receipts/restic-snapshots-latest.json`
- `receipts/sbom/host-docker-runtime-lv3-2026-04-02.cdx.json`
- `workstreams.yaml`

## Expected Live Surfaces

- `https://ops.lv3.org#activation` renders the ADR 0310 checklist and preserves
  progress across normal browser-session refreshes
- launcher entries with purpose `administer` stay out of the navigable entry
  set until activation completes or the supervised reveal path is used
- mutating service actions and mutating runbooks fail closed server-side until
  the same activation guard is satisfied
- the managed ops-portal replay verifies `/partials/activation` in addition to
  the existing launcher and runtime-assurance partials

## Exact-Main Verification

- `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-release-status-r1.json`,
  `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-release-dry-run-r10.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-release-manager-r11.txt`,
  and `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-release-manager-r12.txt`
  capture the refreshed exact-main release cut on top of repository version
  `0.177.143`. `release-manager-r11.txt` truthfully preserves the first
  generator failure while `workstreams.yaml` still used absolute worktree and
  workstream-doc paths, and `release-manager-r12.txt` preserves the follow-on
  no-op write after the release surfaces had already been cut.
- `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-py-compile-r2.txt`
  confirms the focused syntax lane passed for
  `scripts/ops_portal/app.py`, `scripts/operator_manager.py`,
  `scripts/journey_scorecards.py`, and
  `config/windmill/scripts/command-palette-search.py`.
- `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-targeted-tests-r16.txt`
  shows `53 passed in 5.01s` for the interactive ops portal, runtime-role,
  playbook, command-palette, and Windmill operator-admin regression slice from
  the exact-main release tree.
- `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-live-apply-r12.txt`
  truthfully preserves the first exact-main replay failure, where canonical
  truth blocked the run because `README.md` had not yet been regenerated after
  the `0.177.144` cut. `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-canonical-truth-r1.txt`
  records the repair, and
  `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-live-apply-r13.txt`
  captured the successful governed replay with final recap
  `docker-runtime-lv3 : ok=192 changed=17 unreachable=0 failed=0 skipped=36`.
- `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-ops-portal-guest-runtime-r21.txt`
  confirms the guest-local guarded journey through the repo-managed Proxmox
  jump path: `/health` returned `{"status":"ok"}`, activation and launcher
  partials stayed locked before checklist completion, mutating service actions
  failed closed while locked, completing the required items unlocked the admin
  launcher redirect to `https://sso.lv3.org`, and the policy override path
  produced the same unlocked launcher outcome.
- `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-generate-adr-index-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-canonical-truth-r2.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-platform-manifest-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-generate-diagrams-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-generate-platform-vars-r1.txt`,
  and `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-agent-standards-r1.txt`
  record the regenerated truth surfaces needed after the `0.177.144` /
  `0.130.91` promotion.
- `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-workstream-surfaces-r1.txt`
  truthfully preserves the first ownership failure, where `Makefile`,
  `playbooks/ops-portal.yml`, and
  `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
  had not yet been declared for ws-0310. `...workstream-surfaces-r2.txt`
  passed after the manifest was expanded to cover the full live-apply
  automation footprint plus the regenerated platform vars surface.
- `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-validate-data-models-r1.txt`
  and
  `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-live-apply-receipts-validate-r1.txt`
  preserve the first receipt-schema failure, where the new canonical receipt
  referenced future evidence files before those runs existed. The repaired
  reruns in `...validate-data-models-r2.txt` and
  `...live-apply-receipts-validate-r2.txt` passed after the missing evidence
  paths were created and then overwritten with the real outputs.
- `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-validate-r1.txt`
  shows the first `make validate` failure on stale
  `inventory/group_vars/platform.yml` after the platform-version bump;
  `...generate-platform-vars-r1.txt` repaired that generated surface.
  `...validate-r2.txt` then preserved the follow-on receipt-reference failure,
  and `...validate-r3.txt` is the authoritative passing local validation bundle
  from the repaired tree.
- `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-remote-validate-r1.txt`
  and `...remote-validate-r2.txt` preserve the first two remote-lane attempts,
  where immutable snapshot uploads to the build server failed with
  `No space left on device` and the command fell back locally.
  `...check-build-server-r1.txt` confirmed the build-server path itself was
  reachable, and
  `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-remote-build-server-cleanup-r1.txt`
  records the manual removal of two stale April 1 session workspaces on
  `10.10.10.30`, which restored roughly `46G` free space. After that repair,
  `...remote-validate-r3.txt` passed on the intended remote builder path.
- `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-pre-push-gate-r1.txt`
  preserves the first full gate failure, where the build-server disk issue
  forced a local fallback and several heavy lanes timed out.
  `...pre-push-gate-r2.txt` is the authoritative remote pass after the stale
  session-workspace cleanup restored the build-server snapshot path.
- `receipts/live-applies/evidence/2026-04-02-ws-0310-mainline-git-diff-check-r1.txt`
  confirms the final tracked tree is free of whitespace and merge-marker drift.

## Results

- ADR 0310 is live on the interactive ops portal runtime and preserved by its
  standalone exact-main receipt.
- Repository version `0.177.144` and platform version `0.130.91` now describe
  one exact-main activation-checklist replay, including the server-side
  launcher, runbook, and service-action guardrails.
- The correction loop strengthened the promotion path by exposing two real
  integration risks on the latest lineage: generator consumers need repository-
  relative workstream metadata, and canonical truth must be refreshed before a
  promoted replay can proceed.
- The broader validation rehearsal also exposed one infrastructure issue
  outside the repo tree: the remote build server had filled `/home/ops/builds`
  with stale session workspaces, so completing the intended remote validation
  path required a documented manual cleanup of two abandoned April 1
  workspaces.
- The later combined ws-0308 exact-main replay carried the same activation
  behavior forward as the current mainline `ops_portal` receipt at repository
  version `0.177.146` and platform version `0.130.92`.

## Mainline Note

The protected release and canonical-truth surfaces from the standalone ADR 0310
replay remain preserved by its receipt, and the later combined ws-0308 portal
bundle now carries that activation contract on the current mainline. No
separate ws-0310 merge-only repo surfaces remain.
