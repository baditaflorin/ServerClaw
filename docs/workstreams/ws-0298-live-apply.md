# Workstream ws-0298-live-apply: Live Apply ADR 0298 From Latest `origin/main`

- ADR: [ADR 0298](../adr/0298-syft-and-grype-for-platform-wide-sbom-generation-and-continuous-cve-scanning.md)
- Title: Live apply platform-wide SBOM generation and continuous CVE scanning with Syft and Grype
- Status: live_applied
- Included In Repo Version: 0.177.118
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0298-sbom-cve-scanning-branch-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-31-adr-0298-sbom-cve-scanning-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.77
- Implemented On: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0298-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0298-live-apply-r2`
- Owner: codex
- Depends On: `adr-0068`, `adr-0087`, `adr-0102`, `adr-0165`, `adr-0295`
- Conflicts With: none

## Purpose

Implement ADR 0298 by pinning Syft and Grype, wiring the managed-image
validation gate, adding the daily Windmill refresh workflow, and making host
SBOM generation part of the governed converge and security-scan paths.

## Final Outcome

- The final live apply was replayed from the exact `origin/main`
  baseline `5c7e07235f7b0da1f756148e145397f0ac6ceb10` using the isolated
  mainline worktree
  `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0298-main-final-r4`.
- `make converge-windmill` corrected the shared
  `/srv/proxmox_florin_server` mirror on `docker-runtime-lv3`, restoring the
  committed `config/windmill/scripts/sbom-refresh.py` wrapper and the patched
  `scripts/sbom_scanner.py` native-tooling logic.
- The governed replay recap was
  `docker-runtime-lv3 : ok=330 changed=50 failed=0 skipped=70`,
  `postgres-lv3 : ok=76 changed=5 failed=0 skipped=20`, and
  `proxmox_florin : ok=41 changed=4 failed=0 skipped=16`.
- The live native worker now exposes `/usr/local/bin/syft` `1.41.2` and
  `/usr/local/bin/grype` `0.110.0`, and the scanner writes extraction scratch
  data under the repo-local `.local/syft-tmp` contract.
- The authoritative worker-side wrapper replay completed from the live exact-main
  checkout with `rc=0`, `status: ok`, and `Scanned 62 managed images`.

## Mainline Verification

- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-targeted-pytest-r2.txt`
  records the exact-main focused pytest bundle passing with `23 passed`.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-py-compile-r2.txt`
  records a clean `python3 -m py_compile` pass for `scripts/sbom_scanner.py`.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-converge-windmill-r2.txt`
  records the governed Windmill replay that refreshed the worker checkout and
  runtime compose surfaces on `docker-runtime-lv3`.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-live-checkout-r3.txt`
  confirms the live worker mirror contains `DEFAULT_SYFT_TMP_DIR`,
  `LV3_SYFT_TMP_DIR`, and `find_native_grype_binary()`.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-worker-runtime-verify-r2.txt`
  confirms the running native worker exposes the mounted `syft` and `grype`
  binaries at the expected versions.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-mainline-worker-wrapper-r17-poll-r3.txt`
  captures the final host-side wrapper poll with `rc=0`, `status: ok`, and
  `Scanned 62 managed images`.

## Preserved Prior Evidence

- `receipts/live-applies/2026-03-30-adr-0298-sbom-cve-scanning-branch-live-apply.json`
  remains in the branch history as the intentionally blocked branch-local proof
  set that documented the earlier artifact-cache instability and shared worker
  checkout drift.
- The exact-main live apply supersedes that blocked result by proving the
  current `main` checkout can reconverge the worker mirror and complete the full
  catalog refresh from `docker-runtime-lv3`.

## Mainline Notes

- Release `0.177.118` is the first mainline release that records ADR 0298 as
  both implemented and live-applied.
- Platform version `0.130.77` is the first platform version that records the
  exact-main Syft and Grype replay as verified on the live Windmill native
  worker.
