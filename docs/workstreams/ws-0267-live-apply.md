# Workstream WS-0267: Expiring Gate Bypass Waivers Live Apply

- ADR: [ADR 0267](../adr/0267-expiring-gate-bypass-waivers-with-structured-reason-codes.md)
- Title: Refresh ADR 0267 onto the newest realistic `origin/main`, replay the governed waiver surfaces live, and leave the branch ready for the protected mainline merge
- Status: ready_for_merge
- Included In Repo Version: 0.177.105
- Exact-Main Replay Source Version: 0.177.104
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0267-gate-bypass-waivers-live-apply.json`
- Canonical Mainline Receipt: pending merge-to-main
- Live Applied In Platform Version: 0.130.70
- Observed Platform Baseline During Replay: 0.130.69
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0267-main-refresh-v5`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0267-main-refresh-v5`
- Owner: codex
- Depends On: `adr-0087-validation-gate`, `adr-0168-automated-validation`, `adr-0228-windmill-default-operations-surface`, `adr-0230-policy-decisions-via-open-policy-agent-and-conftest`
- Conflicts With: none

## Scope

- keep validation-gate bypasses governed as structured waivers with reason codes, substitute evidence, owners, and expiry
- keep `gate-status`, release readiness, and the Windmill seeded worker checkout aligned with the waiver catalog and helper code
- refresh ADR 0267 against the newest realistic `origin/main` and leave exact proof for the protected `main` integration step

## Verification

- The exact-main regression slice in `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-targeted-checks-r3-0.177.104.txt` passed with `100 passed in 5.59s`, covering the governed waiver helpers, Windmill validation-gate wiring, repo-surface merge logic, the Docker runtime nftables repair, Docker publication helper replay checks, and the OpenBao helper regression surface.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-syntax-check-r3-0.177.104.txt` confirmed `make syntax-check-windmill` still succeeds from the exact `0.177.104` tree.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-converge-windmill-r3-0.177.104.txt` captured the authoritative latest-main replay with final recap `docker-runtime-lv3 : ok=295 changed=46 unreachable=0 failed=0 skipped=61`, `postgres-lv3 : ok=68 changed=0 unreachable=0 failed=0 skipped=20`, and `proxmox_florin : ok=41 changed=4 unreachable=0 failed=0 skipped=16`.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-gate-status-r2-0.177.104.txt` confirmed the live governed waiver summary remains `0 open, 63 legacy, 0 warnings, 0 release blockers`.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-release-status-r2-0.177.104.txt` confirmed the current repo baseline `0.177.104`, platform baseline `0.130.69`, and that no other workstreams remain in progress on the exact-main tree before the protected merge step.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-host-runtime-r2-0.177.104.txt` reconfirmed hostname `Debian-trixie-latest-amd64-base`, kernel `6.17.13-2-pve`, active `pveproxy` plus `tailscaled`, listeners on `2222`, `8005`, and `8006`, `sudo qm status 120` returning `status: running`, and Windmill answering `CE v1.662.0`.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-generate-adr-index-r2-0.177.104.txt`, `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-validate-repo-r4-0.177.104.txt`, `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-git-diff-check-r4-0.177.104.txt`, and `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-live-apply-receipts-validate-r3-0.177.104.txt` confirm the ADR index refresh, agent/workstream/data-model validation, clean diff state, and receipt-schema validation all pass with the refreshed branch-local receipt and nftables repair in place.

## Results

- ADR 0267 is replayed successfully from the exact `origin/main` tip `d17509656cb97986062852127a6e6ae00deaab27`, superseding the older `f20b44a` and `a01ea4ec6` proof bundles.
- The governed waiver summary is live on the current platform state, and the Windmill worker checkout still mirrors the critical validation-gate integrity files before verification.
- The latest-main replay preserved the earlier repo-root Docker publication helper repair and Docker apt lock tolerance, and it also surfaced then fixed one new latest-main defect: the Docker runtime nftables forward-compat patch now accepts either `ct state established,related` or `ct state related,established` and inserts each Docker CIDR rule deterministically instead of relying on a brittle multi-line `lineinfile` block.

## Remaining For Merge-To-Main

- Create the canonical mainline receipt `receipts/live-applies/2026-03-30-adr-0267-gate-bypass-waivers-mainline-live-apply.json`.
- Refresh the protected integration surfaces from `main`: `VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`, `RELEASE.md`, release notes, and any regenerated canonical truth artifacts they drive.
- Re-run the final mainline validations from `main`, then push `origin/main`.

## Notes

- Historical legacy bypass receipts under `receipts/gate-bypasses/` remain untouched by this workstream.
- The worker checkout integrity sentinel must continue to include both `scripts/gate_bypass_waivers.py` and `config/gate-bypass-waiver-catalog.json`; dropping either lets the seeded Windmill gate-status surface drift silently.
