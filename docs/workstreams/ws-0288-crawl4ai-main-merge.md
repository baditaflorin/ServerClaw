# Workstream ws-0288-crawl4ai-main-merge: ADR 0288 Crawl4AI Exact-Main Integration

- ADR: [ADR 0288](../adr/0288-crawl4ai-as-the-llm-optimised-web-content-crawler.md)
- Title: integrate the private Crawl4AI runtime onto the latest `origin/main` without disturbing the already-merged Flagsmith ws-0288 records
- Status: ready_for_merge
- Included In Repo Version: 0.177.114
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
  `60 passed in 8.11s` across the Crawl4AI runtime, metadata, docker bridge
  helper, docker runtime role, and generated platform vars tests on the
  rebased `0.177.114` tree, and the targeted role regression added for the
  Docker-chain classifier fix returned `11 passed in 0.34s`.
- `make syntax-check-crawl4ai` passed from the final rebased worktree after
  the Docker-chain recovery patch.
- `make converge-crawl4ai` first succeeded from clean source commit
  `58b38c6219c202f3b10766ae8fca5e87dfbeff51`, then succeeded again on the
  final rebased `0.177.114` tree with recap
  `docker-runtime-lv3 : ok=106 changed=4 unreachable=0 failed=0 skipped=10
  rescued=0 ignored=0`.
- Independent verification succeeded for local health, monitor, markdown crawl,
  guest-network reachability from `coolify-lv3`, and the dedicated
  `crawl4ai_runtime` bridge network. Evidence lives under
  `receipts/live-applies/evidence/2026-03-31-ws-0288-crawl4ai-mainline-*.txt`.
- `make validate`, `make remote-validate`, and `make pre-push-gate` all passed
  on the final `0.177.114 / 0.130.75` tree after repairing a Bash 3.2 empty
  array expansion in `scripts/validate_repo.sh`, Python 3.9 callback
  compatibility in `scripts/mutation_audit.py` and the structured-log callback,
  the mirrored `release_tracks.platform_versioning.current` stack field, and
  the Crawl4AI startup failure classifier for missing Docker `DOCKER`
  iptables chains.
- This workstream is branch-complete and ready for the final `main` merge; the
  branch-local exact-main evidence remains the audit trail for the first
  verified `0.177.113 / 0.130.75` promotion and the final rebased
  `0.177.114 / 0.130.75` replay.
