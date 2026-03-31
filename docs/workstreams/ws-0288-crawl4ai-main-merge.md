# Workstream ws-0288-crawl4ai-main-merge: ADR 0288 Crawl4AI Exact-Main Integration

- ADR: [ADR 0288](../adr/0288-crawl4ai-as-the-llm-optimised-web-content-crawler.md)
- Title: integrate the private Crawl4AI runtime onto the latest `origin/main` without disturbing the already-merged Flagsmith ws-0288 records
- Status: merged
- Included In Repo Version: 0.177.115
- Canonical Mainline Receipt: `2026-03-31-adr-0288-crawl4ai-mainline-live-apply`
- Live Applied In Platform Version: 0.130.75
- Branch: `codex/ws-0288-crawl4ai-main-merge-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0288-crawl4ai-main-merge-r2`
- Owner: codex
- Depends On: none
- Conflicts With: `ws-0288-live-apply`, `ws-0288-main-merge`

## Naming Note

The existing `ws-0288-*` records on `origin/main` belong to the already-merged
Flagsmith ADR branch that shares the same numeric ADR identifier. This
collision-safe workstream keeps the Crawl4AI exact-main integration separate so
the registry and workstream docs stay merge-safe.

## Scope

- carry the Crawl4AI runtime, private service topology, health probes, SLOs,
  workflow metadata, image pinning, and verification surfaces onto the latest
  `origin/main`
- keep Crawl4AI off Docker's legacy default `bridge` by using a compose-managed
  bridge network and preserving the bridge-recovery hardening that was proven
  during the earlier live-apply correction loop
- record exact-main live-apply evidence and then update the protected release
  and platform truth surfaces only after the mainline replay is verified

## Current Verification

- Focused repository regression slice passed:
  `60 passed in 3.71s` across the Crawl4AI runtime, metadata, docker bridge
  helper, docker runtime role, and generated platform vars tests on the exact
  `0.177.115` tree from source commit
  `2b04836bc154ee415b0e84427973a14ebe15da59`.
- `make syntax-check-crawl4ai` passed on the exact `0.177.115` tree.
- `make converge-crawl4ai` succeeded from exact source commit
  `2b04836bc154ee415b0e84427973a14ebe15da59`; after a concurrent clean stop
  left the live `crawl4ai` container exited during receipt capture, a second
  governed exact-tree converge restored the service and reran the role-local
  verification tasks with recap
  `docker-runtime-lv3 : ok=113 changed=6 unreachable=0 failed=0 skipped=27
  rescued=1 ignored=0`.
- Independent verification succeeded for local health, monitor, markdown crawl,
  guest-network reachability from `coolify-lv3`, and the dedicated
  `crawl4ai_runtime` bridge network. Evidence lives under
  `receipts/live-applies/evidence/2026-03-31-ws-0288-crawl4ai-mainline-*-0.177.115.txt`.
- `make validate`, `make remote-validate`, and `make pre-push-gate` all passed
  on the final `0.177.115 / 0.130.75` tree after repairing a Bash 3.2 empty
  array expansion in `scripts/validate_repo.sh`, Python 3.9 callback
  compatibility in `scripts/mutation_audit.py` and the structured-log callback,
  the mirrored `release_tracks.platform_versioning.current` stack field, and
  the Crawl4AI startup failure classifier for missing Docker `DOCKER`
  iptables chains.
- During the protected `main` push on 2026-03-31, the build-server snapshot
  upload failed because `/home/ops/builds/proxmox_florin_server` on
  `docker-build-lv3` was full; the recovery was a bounded `sudo rm -rf` of only
  stale remote `ws-0288-*` session workspaces under
  `.lv3-session-workspaces/`, which restored `6.4G` free and kept the cleanup
  within the runbook guidance for remote snapshot failures.
- This workstream is now merged on `main`; the branch-local exact-main
  evidence remains the audit trail for replaying ADR 0288 onto the latest
  realistic `origin/main` baseline `0.177.114 / 0.130.74` and promoting the
  result as `0.177.115 / 0.130.75`.
