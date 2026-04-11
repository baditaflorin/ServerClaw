# Workstream WS-0267: Expiring Gate Bypass Waivers Live Apply

- ADR: [ADR 0267](../adr/0267-expiring-gate-bypass-waivers-with-structured-reason-codes.md)
- Title: Refresh ADR 0267 onto the newest realistic `origin/main`, replay the governed waiver surfaces live, and leave the branch ready for the protected mainline merge
- Status: merged
- Included In Repo Version: 0.177.105
- Exact-Main Replay Source Version: 0.177.104
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0267-gate-bypass-waivers-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0267-gate-bypass-waivers-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.70
- Observed Platform Baseline During Replay: 0.130.69
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0267-mainline-final`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0267-mainline-final`
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
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-converge-windmill-r3-0.177.104.txt` captured the authoritative latest-main replay with final recap `docker-runtime : ok=295 changed=46 unreachable=0 failed=0 skipped=61`, `postgres : ok=68 changed=0 unreachable=0 failed=0 skipped=20`, and `proxmox-host : ok=41 changed=4 unreachable=0 failed=0 skipped=16`.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-gate-status-r2-0.177.104.txt` confirmed the live governed waiver summary remains `0 open, 63 legacy, 0 warnings, 0 release blockers`.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-release-status-r2-0.177.104.txt` confirmed the current repo baseline `0.177.104`, platform baseline `0.130.69`, and that no other workstreams remain in progress on the exact-main tree before the protected merge step.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-host-runtime-r2-0.177.104.txt` reconfirmed hostname `proxmox-host`, kernel `6.17.13-2-pve`, active `pveproxy` plus `tailscaled`, listeners on `2222`, `8005`, and `8006`, `sudo qm status 120` returning `status: running`, and Windmill answering `CE v1.662.0`.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-generate-adr-index-r2-0.177.104.txt`, `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-validate-repo-r4-0.177.104.txt`, `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-git-diff-check-r4-0.177.104.txt`, and `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-live-apply-receipts-validate-r3-0.177.104.txt` confirm the ADR index refresh, agent/workstream/data-model validation, clean diff state, and receipt-schema validation all pass with the refreshed branch-local receipt and nftables repair in place.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-release-dry-run-r1-0.177.105.txt` and `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-release-write-r1-0.177.105.txt` confirm the protected mainline integration step saw one unreleased ADR 0267 note on top of `0.177.104`, then cut repository release `0.177.105` with the expected platform-impact summary.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-canonical-truth-write-r3-0.177.105.txt` confirms the final integration tree refreshed canonical truth after the mainline receipt was recorded, advancing `versions/stack.yaml` to platform version `0.130.70` and replacing `live_apply_evidence.latest_receipts.validation_gate` with the ADR 0267 canonical receipt.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-release-status-r3-0.177.105.txt`, `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-canonical-truth-check-r1-0.177.105.txt`, `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-platform-manifest-check-r2-0.177.105.txt`, `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-live-apply-receipts-validate-r5-0.177.105.txt`, and `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-git-diff-check-r6-0.177.105.txt` confirm the merged tree is internally consistent at repository version `0.177.105` and platform version `0.130.70`.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-validate-repo-r7-0.177.105.txt` shows the passable repo-validation bundle (`agent-standards`, `data-models`, and `generated-docs`) all passed on the merged tree after the platform manifest refresh.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-validate-workstream-surfaces-r1-0.177.105.txt` records the expected terminal-branch guard for `./scripts/validate_repo.sh workstream-surfaces`: once `ws-0267-live-apply` is terminal, the validator intentionally rejects validating it from non-`main` branch `codex/ws-0267-mainline-final`.
- `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-remote-validate-r1-0.177.105.txt` and `receipts/live-applies/evidence/2026-03-30-ws-0267-mainline-pre-push-gate-r1-0.177.105.txt` prove both wrapper entry points were exercised end to end; in both cases every other reported lane passed, while the only blockers were the same expected terminal-branch `workstream-surfaces` guard and one unrelated existing `mypy` runner defect (`platform/repo.py:231` missing `PyYAML` stubs in the check-runner image).

## Results

- ADR 0267 is replayed successfully from the exact `origin/main` tip `d17509656cb97986062852127a6e6ae00deaab27`, superseding the older `f20b44a` and `a01ea4ec6` proof bundles.
- The governed waiver summary is live on the current platform state, and the Windmill worker checkout still mirrors the critical validation-gate integrity files before verification.
- The latest-main replay preserved the earlier repo-root Docker publication helper repair and Docker apt lock tolerance, and it also surfaced then fixed one new latest-main defect: the Docker runtime nftables forward-compat patch now accepts either `ct state established,related` or `ct state related,established` and inserts each Docker CIDR rule deterministically instead of relying on a brittle multi-line `lineinfile` block.
- The protected mainline integration step cut repository release `0.177.105`, recorded `receipts/live-applies/2026-03-30-adr-0267-gate-bypass-waivers-mainline-live-apply.json` as the canonical proof, and advanced the tracked platform baseline to `0.130.70`.

## Merge Completion

- The integrated tree now carries the protected release and canonical-truth surfaces on top of the exact-main replay.
- The remaining closeout work is the `origin/main` push from this worktree.

## Notes

- Historical legacy bypass receipts under `receipts/gate-bypasses/` remain untouched by this workstream.
- The worker checkout integrity sentinel must continue to include both `scripts/gate_bypass_waivers.py` and `config/gate-bypass-waiver-catalog.json`; dropping either lets the seeded Windmill gate-status surface drift silently.
- The repo automation wrappers currently surface one unrelated baseline issue while validating this terminal branch: the `type-check` lane fails in the runner image because `platform/repo.py` imports `yaml` without installed `PyYAML` stubs. ADR 0267 does not modify that module, but the evidence above records the current blocker explicitly.
