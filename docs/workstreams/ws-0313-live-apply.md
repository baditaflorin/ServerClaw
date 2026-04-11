# Workstream ws-0313-live-apply: Live Apply ADR 0313 From Latest `origin/main`

- ADR: [ADR 0313](../adr/0313-contextual-help-glossary-and-escalation-drawer.md)
- Title: Ship the shared contextual help, glossary, and escalation drawer across the first-party portal surfaces
- Status: live_applied
- Included In Repo Version: 0.177.139
- Branch-Local Receipt: `receipts/live-applies/2026-04-02-adr-0313-contextual-help-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0313-contextual-help-mainline-live-apply.json`
- Branch-Local Replay Source Commit: `154564f3c2433d5dd0b295a64c34272fd3b7f956`
- Branch-Local Replay Repo Version: `0.177.136`
- Branch-Local Replay Platform Version: `0.130.85`
- Live Applied In Platform Version: 0.130.87
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Exact-Main Replay Baseline: repo `0.177.138`, platform `0.130.86`
- Branch: `codex/ws-0313-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0313-live-apply`
- Owner: codex
- Depends On: `adr-0093`, `adr-0094`, `adr-0134`, `adr-0235`, `adr-0242`, `adr-0312`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0313-live-apply.md`, `docs/adr/0313-contextual-help-glossary-and-escalation-drawer.md`, `docs/adr/.index.yaml`, `docs/runbooks/platform-operations-portal.md`, `docs/runbooks/developer-portal.md`, `docs/runbooks/deployment-history-portal.md`, `docs/runbooks/ops-portal-down.md`, `docs/runbooks/docker-runtime-bridge-chain-loss.md`, `scripts/portal_utils.py`, `scripts/generate_ops_portal.py`, `scripts/generate_docs_site.py`, `scripts/generate_changelog_portal.py`, `scripts/search_fabric/utils.py`, `scripts/ops_portal/`, `docs/templates/reference-index.md.j2`, `docs/templates/reference-glossary.md.j2`, `docs/theme-overrides/`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`, `collections/ansible_collections/lv3/platform/roles/linux_guest_firewall/tasks/main.yml`, `tests/test_ops_portal.py`, `tests/test_interactive_ops_portal.py`, `tests/test_docs_site.py`, `tests/test_changelog_portal.py`, `tests/test_ops_portal_playbook.py`, `tests/test_ops_portal_runtime_role.py`, `tests/test_linux_guest_firewall_role.py`, `receipts/live-applies/`, `receipts/live-applies/evidence/`

## Purpose

Implement ADR 0313 from the latest realistic `origin/main` baseline by adding a
shared contextual-help model that works across the repo-owned browser surfaces,
then replay the live publication paths and record enough verification evidence
for a safe exact-main merge.

## Scope

- add a reusable contextual-help and glossary model for the first-party portal
  surfaces
- wire the drawer into the interactive ops portal runtime and the generated ops
  portal snapshot
- surface the same help model in the generated docs and changelog portals
- add or refresh operational docs so operators know how to verify the new help
  affordance
- verify the relevant portal generators, runtime role checks, and live edge
  publication paths end to end

## Non-Goals

- replacing the full runbooks or ADR corpus with drawer content
- modifying third-party product-native UIs that the platform links out to
- updating protected release and canonical-truth surfaces on this workstream
  branch before the exact-main integration step

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0313-live-apply.md`
- `docs/adr/0313-contextual-help-glossary-and-escalation-drawer.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/platform-operations-portal.md`
- `docs/runbooks/developer-portal.md`
- `docs/runbooks/deployment-history-portal.md`
- `docs/runbooks/ops-portal-down.md`
- `docs/runbooks/docker-runtime-bridge-chain-loss.md`
- `scripts/portal_utils.py`
- `scripts/generate_ops_portal.py`
- `scripts/generate_docs_site.py`
- `scripts/generate_changelog_portal.py`
- `scripts/search_fabric/utils.py`
- `scripts/ops_portal/`
- `docs/templates/reference-index.md.j2`
- `docs/templates/reference-glossary.md.j2`
- `docs/theme-overrides/`
- `docs/site-generated/architecture/dependency-graph.md`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`
- `collections/ansible_collections/lv3/platform/roles/linux_guest_firewall/tasks/main.yml`
- `receipts/ops-portal-snapshot.html`
- `tests/test_ops_portal.py`
- `tests/test_interactive_ops_portal.py`
- `tests/test_docs_site.py`
- `tests/test_changelog_portal.py`
- `tests/test_ops_portal_playbook.py`
- `tests/test_ops_portal_runtime_role.py`
- `tests/test_linux_guest_firewall_role.py`
- `receipts/live-applies/`
- `receipts/live-applies/evidence/`

## Expected Live Surfaces

- `https://ops.example.com` serves the live interactive portal with the contextual
  help drawer on the root page
- `https://docs.example.com` serves generated docs pages with page-scoped help and
  a published glossary reference
- `https://changelog.example.com` serves deployment-history pages with the same
  glossary and escalation affordance
- repo-managed verification paths fail closed if the ops portal root page loses
  the help drawer contract during future replays

## Branch-Local Verification

- `receipts/live-applies/evidence/2026-04-02-ws-0313-portal-import-fix-tests-r1.txt`
  shows `28 passed in 2.14s` for the interactive portal runtime and role
  regression slice after the image-layout import fix.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-portal-full-suite-r2.txt`
  shows `51 passed in 54.36s` across the ops, docs, changelog, playbook, and
  runtime-role surfaces.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-ops-portal-syntax-check-r2.txt`
  confirms `make syntax-check-ops-portal` passed from this worktree.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-ops-portal-direct-replay-r8.txt`
  captured the authoritative governed replay with final recap
  `docker-runtime : ok=185 changed=12 unreachable=0 failed=0 skipped=36`.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-ops-portal-guest-runtime-r2.txt`
  confirms the live `ops-portal` container is healthy on `docker-runtime`,
  `/health` returns `{"status":"ok"}`, and the running root page contains
  `Contextual Help`, `Escalation Path`, `Live apply`, `Runtime Assurance`, and
  `Application Launcher`.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-deploy-docs-portal-r1.txt`
  captured the shared-edge publication replay with final recap
  `nginx-edge : ok=86 changed=5 unreachable=0 failed=0 skipped=18`.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-portal-public-verification-r1.txt`
  confirms the generated docs and changelog artifacts still carry the drawer
  markers, the local `index.html` digests match the deployed copies under
  `/var/www/lv3-generated/`, and public requests to `https://ops.example.com/`,
  `https://docs.example.com/`, and `https://changelog.example.com/` all return the
  expected unauthenticated `302` redirects.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-adr-index-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-workstream-surface-validation-r3.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-live-apply-receipts-validation-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-repo-validation-r3.txt`,
  and `receipts/live-applies/evidence/2026-04-02-ws-0313-git-diff-check-r1.txt`
  confirm the refreshed ADR index, branch ownership manifest, live-apply
  receipt schema, repo validation bundle, and `git diff --check` all passed on
  the final tracked branch-local state.

## Exact-Main Verification

- `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-syntax-check-r2.txt`
  confirms `make syntax-check-ops-portal` passed from the rebased
  `codex/ws-0313-main-integration` tree.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-targeted-tests-r3.txt`
  truthfully preserves the first rebased test-slice failure, where the
  docs-only UV environment no longer provided `fastapi` for
  `tests/test_interactive_ops_portal.py`.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-targeted-tests-r4.txt`
  shows `56 passed in 60.20s` after rerunning the same slice with
  `requirements/ops-portal.txt` added to the UV environment.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-release-status-r2.json`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-release-manager-dry-run-r3.txt`,
  and `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-release-manager-r2.txt`
  capture the refreshed exact-main release cut on top of repository version
  `0.177.138`, including the single ADR 0313 unreleased note and the prepared
  `0.177.139` release bundle.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-live-apply-r2.txt`
  captured the refreshed exact-main governed replay with final recap
  `docker-runtime : ok=189 changed=14 unreachable=0 failed=0 skipped=36`
  plus the follow-on restic backup trigger.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-ops-portal-guest-runtime-r6.txt`
  confirms the refreshed live `ops-portal` container is healthy on
  `docker-runtime`, `/health` returns `{"status":"ok"}`, and the root page
  still exposes `Contextual Help`, `Escalation Path`, `Live apply`,
  `Runtime Assurance`, and `Application Launcher`.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-deploy-docs-portal-r1.txt`
  captures the shared-edge publication replay that republishes the final docs
  and changelog portals from the `0.177.139` tree.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-portal-public-verification-r1.txt`
  truthfully preserves the first public-verification parser false negative on
  `X-Robots-Tag`.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-portal-public-verification-r2.txt`
  confirms the generated docs and changelog artifacts carry the drawer markers,
  the local `index.html` digests match the deployed copies under
  `/var/www/lv3-generated/`, and public requests to `https://ops.example.com/`,
  `https://docs.example.com/`, and `https://changelog.example.com/` still return the
  expected unauthenticated `302` redirects.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-generate-adr-index-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-canonical-truth-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-platform-manifest-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-generate-diagrams-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-generate-dependency-diagram-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-generate-dependency-diagram-r2.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-validate-data-models-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-workstream-surfaces-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-workstream-surfaces-r2.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-workstream-surfaces-r3.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-live-apply-receipts-validate-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-live-apply-receipts-validate-r2.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-validate-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-validate-r2.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-validate-r3.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-remote-validate-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-pre-push-gate-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-pre-push-gate-r2.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-git-diff-check-r1.txt`,
  and `receipts/live-applies/evidence/2026-04-02-ws-0313-mainline-git-diff-check-r2.txt`
  record the regenerated truth surfaces plus the final repo automation and
  validation gates from the integrated release tree. `workstream-surfaces-r1`
  truthfully preserves the initial failure before repo-local scratch files were
  removed and the refreshed restic/SBOM outputs were declared, `validate-r1`
  preserves the controller disk-pressure failure while ADR 0230 policy
  validation tried to install OPA with only `128MiB` free, and `validate-r2`
  preserves the stale dependency-graph failure before
  `generate-dependency-diagram-r2.txt` refreshed the generated markdown.

## Results

- ADR 0313 is now live on the interactive ops portal runtime, the generated ops
  snapshot, the docs portal, and the changelog portal.
- The exact-main replay had to be restarted after `origin/main` advanced to
  `0.177.138` during the first integration attempt, so the canonical promotion
  now records the refreshed `0.177.139` repo cut on platform version
  `0.130.87`.
- The branch-local replay surfaced and fixed two real defects that only became
  obvious under the latest live lineage: Docker bridge chains could disappear
  after nftables evaluation on `docker-runtime`, and the mirrored runtime
  tree imported `platform.datetime_compat` even though the isolated image layout
  does not ship the repo `platform` package.
- The runtime receipt mirror is now narrower and more durable: it syncs the
  production and staging JSON receipts the portal reads, while intentionally
  excluding `receipts/live-applies/evidence/` transcripts and preview payloads.

## Mainline Note

The protected release and canonical-truth surfaces now reflect the refreshed
exact-main replay on `codex/ws-0313-main-integration`. No merge-only repo
surfaces remain outstanding; the last step is the final `origin/main` sync and
push of this validated tree.
