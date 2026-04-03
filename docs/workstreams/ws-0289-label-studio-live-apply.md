# Workstream ws-0289-label-studio-live-apply: ADR 0289 Label Studio Live Apply

- ADR: [ADR 0289](../adr/0289-label-studio-as-the-human-in-the-loop-data-annotation-platform.md)
- Title: deploy Label Studio from the latest realistic `origin/main` baseline without colliding with the existing Directus `ws-0289-*` records
- Status: live_applied
- Included In Repo Version: 0.177.153
- Canonical Mainline Receipt: `2026-04-03-adr-0289-label-studio-mainline-live-apply`
- Live Applied In Platform Version: 0.130.97
- Branch: `codex/ws-0289-label-studio-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0289-label-studio-live-apply-r1`
- Owner: codex
- Depends On: none
- Conflicts With: `ws-0289-live-apply`

## Naming Note

`origin/main` already contains `ws-0289-live-apply` for the Directus ADR that
shares the same numeric identifier. This collision-safe Label Studio record
keeps the annotation-platform delivery merge-safe by using an explicit
`ws-0289-label-studio-*` namespace for the ADR-local state.

## Scope

- add the repo-managed Label Studio PostgreSQL and runtime roles, playbooks,
  project catalog sync helper, and verification tasks
- carry the private runtime, public edge publication, health probes, SLOs,
  workflow metadata, and service-catalog truth onto the latest realistic
  `origin/main` baseline
- pin the reviewed `docker.io/heartexlabs/label-studio:1.23.0` runtime image
  by digest and record the Trivy scan receipt
- record the branch-local and exact-main live-apply evidence separately so the
  protected release and canonical truth surfaces can be updated only after the
  mainline replay is verified

## Final Mainline State

- Label Studio is live on `docker-runtime-lv3` at private port `8110` with the
  dedicated `label_studio` PostgreSQL database on `postgres-lv3`.
- Browser access is enforced at the shared edge through oauth2-proxy and
  Keycloak, while the app-local admin password and token remain the deterministic
  automation and break-glass path.
- The reviewed runtime image remains
  `docker.io/heartexlabs/label-studio:1.23.0@sha256:aa461572e8f9d86a1bf9520c1db620204e86160fd2f80dd7e9d40ac84a8828ea`
  with Trivy summary `0 critical / 11 high`.
- The latest exact-main replay was performed from merged head `cb7a375c7`
  after `origin/main` advanced to `26e6849be`
  (`[ws-0340] Live apply fixes: chdir, auth-file, API 201/422, migration fallback`).
- During final integration, `origin/main` advanced again to `591eb347c`
  (`[ws-0340] Finalize live apply: HTTP upstream, DB migration, full completion`);
  this closeout preserved that newer ws-0340 state and backfilled its missing
  canonical receipt so the latest-tip repository truth validates cleanly.
- That newer `origin/main` head carried inconsistent repo-version surfaces:
  `VERSION` still read `0.177.152`, while `versions/stack.yaml` already read
  `0.177.153` / `0.130.96`. This workstream treated `0.177.153` as the latest
  realistic baseline, replayed Label Studio there, and then repaired the
  release surfaces during final integration.

## Evidence

- Focused repo validation on the rebased exact-main tree is preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0289-label-studio-mainline-syntax-r1-0.177.152.txt`,
  `receipts/live-applies/evidence/2026-04-03-ws-0289-label-studio-mainline-preflight-r1-0.177.152.txt`,
  and
  `receipts/live-applies/evidence/2026-04-03-ws-0289-label-studio-mainline-pytest-r1-0.177.152.txt`.
- The first exact-main regenerate failure that exposed the stale shared
  `coolify_apps` truth is preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0289-label-studio-mainline-generate-edge-static-sites-r1-0.177.152.txt`;
  the repaired generator pass is preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0289-label-studio-mainline-generate-edge-static-sites-r2-0.177.152.txt`.
- The first post-rebase converge failure that still carried the stale
  generator contract is preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0289-label-studio-mainline-converge-r6-0.177.152.txt`.
- The rebased exact-main replay on the `0.177.152` / `0.130.95` baseline
  succeeded in
  `receipts/live-applies/evidence/2026-04-03-ws-0289-label-studio-mainline-converge-r7-0.177.152.txt`
  with recap `docker-runtime-lv3 ok=518 changed=148 failed=0`, `postgres-lv3
  ok=73 changed=0 failed=0`, `nginx-lv3 ok=100 changed=5 failed=0`, and
  `localhost ok=22 changed=0 failed=0`.
- After merging the newer `origin/main` head, the latest realistic mainline
  replay succeeded in
  `receipts/live-applies/evidence/2026-04-03-ws-0289-label-studio-mainline-converge-r8-0.177.153.txt`
  with recap `docker-runtime-lv3 ok=492 changed=144 failed=0`,
  `postgres-lv3 ok=73 changed=0 failed=0`, `nginx-lv3 ok=100 changed=5
  failed=0`, and `localhost ok=22 changed=0 failed=0`.
- Standalone public shared-edge redirect proofs are preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0289-label-studio-public-head-r3-0.177.152.txt`
  and
  `receipts/live-applies/evidence/2026-04-03-ws-0289-label-studio-public-head-r4-0.177.153.txt`.

## Release Note

- `scripts/release_manager.py` remained blocked on unrelated in-progress
  workstreams `ws-0330-public-github-readiness` and `ws-0340-implementation`,
  so the final `0.177.153` release surfaces were reconciled manually while
  preserving the latest realistic mainline truth and the canonical live-apply
  evidence.
