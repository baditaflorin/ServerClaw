# Workstream ws-0298-main-merge

- ADR: [ADR 0298](../adr/0298-syft-and-grype-for-platform-wide-sbom-generation-and-continuous-cve-scanning.md)
- Title: Integrate ADR 0298 exact-main replay onto `origin/main`
- Status: live_applied
- Included In Repo Version: 0.177.118
- Platform Version Observed During Integration: 0.130.77
- Release Date: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0298-main-final-r4`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0298-main-final-r4`
- Final Exact-Main Replay Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0298-main-final-r4`
- Owner: codex
- Depends On: `ws-0298-live-apply`

## Purpose

Carry the verified ADR 0298 SBOM and CVE scanning surfaces onto the newest
available `origin/main`, rerun the governed worker refresh from committed
source on that synchronized baseline, and update the protected release and
canonical-truth surfaces only after the exact-main live replay succeeds.

## Integration Notes

- `git fetch origin --prune` held the merge baseline on
  `5c7e07235f7b0da1f756148e145397f0ac6ceb10`, which was release `0.177.117`
  before this final ADR 0298 integration pass.
- The exact-main replay preserved the earlier stale-worker evidence instead of
  discarding it, then corrected the shared Windmill mirror with a governed
  `make converge-windmill` from the isolated mainline tree.
- The live runtime now reflects the committed native-worker contract:
  `/usr/local/bin/syft`, `/usr/local/bin/grype`, the Docker socket mount, and
  repo-local Syft scratch extraction under `.local/syft-tmp`.

## Verification

- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-targeted-pytest-r2.txt`
  passed with `23 passed`.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-py-compile-r2.txt`
  passed for `scripts/sbom_scanner.py`.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-converge-windmill-r2.txt`
  recorded the governed exact-main worker resync on `docker-runtime-lv3`.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-live-checkout-r3.txt`
  confirmed the live mirror carries the native Grype detection and Syft temp-dir
  hardening code paths.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-worker-runtime-verify-r2.txt`
  confirmed the running native worker exposes `syft 1.41.2` and `grype 0.110.0`.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-worker-wrapper-r17-poll-r3.txt`
  captured the authoritative worker-side wrapper proof with `rc=0`,
  `status: ok`, and `Scanned 62 managed images`.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-validate-r5.txt`
  exercised `make validate`; after an earlier transient provider checksum
  timeout on the previous attempt, the rerun completed every substantive lane
  and failed only the expected terminal-workstream branch guard.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-generate-dependency-diagram-r5.txt`
  plus
  `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-generated-docs-r1.txt`
  captured the dependency-graph refresh that restored generated-doc freshness
  before the final repo automation replay.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-pre-push-gate-r3.txt`
  records the final pre-push replay: the remote `packer-validate` and
  `tofu-validate` lanes briefly hit `502 Bad Gateway` pulls for
  `registry.lv3.org/check-runner/infra:2026.03.23`, the documented local
  fallback then passed both lanes, and the only remaining non-pass was the
  expected `workstream-surfaces` guard for terminal branch
  `codex/ws-0298-main-final-r4`.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-final-metadata-validate-r1.txt`
  revalidated `data-models`, `generated-docs`, and `agent-standards` after the
  canonical receipt and workstream docs were updated, while
  `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-workstream-surfaces-r1.txt`
  preserved the same expected terminal-branch guard on the exact final tree.

## Outcome

- Release `0.177.118` integrates the final ADR 0298 mainline carry-forward and
  records the first verified platform promotion for this ADR.
- Platform version `0.130.77` now records ADR 0298 as live-applied from the
  exact-main replay on `docker-runtime-lv3`.
- The canonical receipt for this promotion is
  `receipts/live-applies/2026-03-31-adr-0298-sbom-cve-scanning-mainline-live-apply.json`.
- On this dedicated integration branch, the only remaining top-level gate
  non-pass is the designed `workstream-surfaces` terminal-branch guard; that
  branch-scoped check no longer applies after this exact tree lands on `main`.
