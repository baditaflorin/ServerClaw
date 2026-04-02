# Workstream ws-0313-live-apply: Live Apply ADR 0313 From Latest `origin/main`

- ADR: [ADR 0313](../adr/0313-contextual-help-glossary-and-escalation-drawer.md)
- Title: Ship the shared contextual help, glossary, and escalation drawer across the first-party portal surfaces
- Status: ready_for_merge
- Branch-Local Receipt: `receipts/live-applies/2026-04-02-adr-0313-contextual-help-live-apply.json`
- Branch-Local Replay Source Commit: `154564f3c2433d5dd0b295a64c34272fd3b7f956`
- Branch-Local Replay Repo Version: `0.177.136`
- Branch-Local Replay Platform Version: `0.130.85`
- Live Applied On: 2026-04-02
- Latest `origin/main` Awaiting Exact-Main Integration: repo `0.177.137`, platform `0.130.86`
- Branch: `codex/ws-0313-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0313-live-apply`
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

- `https://ops.lv3.org` serves the live interactive portal with the contextual
  help drawer on the root page
- `https://docs.lv3.org` serves generated docs pages with page-scoped help and
  a published glossary reference
- `https://changelog.lv3.org` serves deployment-history pages with the same
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
  `docker-runtime-lv3 : ok=185 changed=12 unreachable=0 failed=0 skipped=36`.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-ops-portal-guest-runtime-r2.txt`
  confirms the live `ops-portal` container is healthy on `docker-runtime-lv3`,
  `/health` returns `{"status":"ok"}`, and the running root page contains
  `Contextual Help`, `Escalation Path`, `Live apply`, `Runtime Assurance`, and
  `Application Launcher`.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-deploy-docs-portal-r1.txt`
  captured the shared-edge publication replay with final recap
  `nginx-lv3 : ok=86 changed=5 unreachable=0 failed=0 skipped=18`.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-portal-public-verification-r1.txt`
  confirms the generated docs and changelog artifacts still carry the drawer
  markers, the local `index.html` digests match the deployed copies under
  `/var/www/lv3-generated/`, and public requests to `https://ops.lv3.org/`,
  `https://docs.lv3.org/`, and `https://changelog.lv3.org/` all return the
  expected unauthenticated `302` redirects.
- `receipts/live-applies/evidence/2026-04-02-ws-0313-adr-index-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-workstream-surface-validation-r3.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-live-apply-receipts-validation-r1.txt`,
  `receipts/live-applies/evidence/2026-04-02-ws-0313-repo-validation-r3.txt`,
  and `receipts/live-applies/evidence/2026-04-02-ws-0313-git-diff-check-r1.txt`
  confirm the refreshed ADR index, branch ownership manifest, live-apply
  receipt schema, repo validation bundle, and `git diff --check` all passed on
  the final tracked branch-local state.

## Results

- ADR 0313 is now live on the interactive ops portal runtime, the generated ops
  snapshot, the docs portal, and the changelog portal.
- The branch-local replay surfaced and fixed two real defects that only became
  obvious under the latest live lineage: Docker bridge chains could disappear
  after nftables evaluation on `docker-runtime-lv3`, and the mirrored runtime
  tree imported `platform.datetime_compat` even though the isolated image layout
  does not ship the repo `platform` package.
- The runtime receipt mirror is now narrower and more durable: it syncs the
  production and staging JSON receipts the portal reads, while intentionally
  excluding `receipts/live-applies/evidence/` transcripts and preview payloads.

## Merge-To-Main Note

This workstream intentionally defers protected surfaces such as `VERSION`,
release sections in `changelog.md`, top-level `README.md`, and
`versions/stack.yaml` until the exact-main integration step. If the branch is
fully live-applied before merge, record the evidence and receipt here so the
mainline replay can update only the protected truth surfaces that must wait.

As of 2026-04-02, this branch is still behind `origin/main`, which already
advanced to repository version `0.177.137` and platform version `0.130.86`.
The final merge-to-main step therefore still has to replay ADR 0313 on that
exact lineage before pushing `origin/main`.
