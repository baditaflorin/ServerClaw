# Workstream ws-0293-livekit-live-apply: Live Apply ADR 0293 From Latest `origin/main`

- ADR: [ADR 0293](../adr/0293-livekit-as-the-real-time-audio-and-voice-channel-for-agents.md)
- Title: Deploy LiveKit as the repo-managed real-time voice transport for operator and agent sessions
- Status: in_progress
- Implemented In Repo Version: pending main integration
- Live Applied In Platform Version: pending verification
- Implemented On: pending verification
- Live Applied On: pending verification
- Branch: `codex/ws-0293-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0293-live-apply-r2`
- Owner: codex
- Depends On: `adr-0021`, `adr-0077`, `adr-0165`, `adr-0191`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0293`, `docs/workstreams/ws-0293-livekit-live-apply.md`, `docs/runbooks/configure-livekit.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `playbooks/livekit.yml`, `playbooks/services/livekit.yml`, `collections/ansible_collections/lv3/platform/roles/livekit_runtime/`, `collections/ansible_collections/lv3/platform/roles/proxmox_network/`, `config/*livekit-related catalogs*`, `build/platform-manifest.json`, `receipts/image-scans/`, `receipts/live-applies/`

## Scope

- converge the repo-managed LiveKit runtime on `docker-runtime-lv3`
- publish signalling through `https://livekit.lv3.org`
- forward public TCP `7881` and UDP `7882` through the Proxmox host for WebRTC media
- verify room lifecycle locally and publicly through the repo-managed helper workflow
- record branch-local live-apply evidence that another agent can merge safely

## Notes

- this workstream was restarted from a fresh worktree on the latest `origin/main` after an earlier checkout accumulated unrelated concurrent edits
- `origin/main` now already contains a different `ws-0293-live-apply` record and document for the Temporal rollout, so this LiveKit stream tracks on `ws-0293-livekit-live-apply` to avoid colliding with the merged mainline truth while preserving the ADR 0293 linkage
- shared integration files such as `README.md`, `VERSION`, `changelog.md`, and `versions/stack.yaml` remain intentionally untouched on this workstream branch until the final main integration step
- `make live-apply-service service=livekit env=production` is expected to fail on this branch before Ansible because `check-canonical-truth` protects the intentionally deferred `README.md` integration summary; the authoritative exact-main replay therefore has to run after the final merge-to-main step, while this branch records the pre-merge converge and verification evidence
- the repo pre-push lane also required a refreshed dependency diagram and `build/platform-manifest.json`; both generated surfaces are now current on this branch, so the remaining push-hook incompatibility is the intentionally deferred canonical-truth write to `README.md`
- the earlier ADR 0153 `vm:120` lock blocker has cleared, but the shared-host replay window is still unstable because concurrent `nginx-lv3`, `docker-runtime-lv3`, and `proxmox_florin` applies keep touching the same runtime and edge surfaces during verification
- the pre-rebase converge evidence remains diagnostically useful: `2026-03-31-ws-0293-livekit-branch-converge-r3.txt` reached successful Proxmox programming, successful guest-local listener and room-lifecycle verification, and successful site-local certificate issuance, then failed only when the public controller-side verify hit a hostname-mismatched certificate after another workstream rewrote `/etc/nginx/sites-available/lv3-edge.conf`
- on `2026-03-31`, this branch was rebased onto `origin/main` commit `58dad5d37ae16ceb3a73bc2fe4554b2a449e8f83` with repo version `0.177.112`; targeted post-rebase validation now passes via `49 passed` across the LiveKit-focused pytest lanes, `make syntax-check-livekit`, and `scripts/validate_repo.sh agent-standards`
- because that rebase changed the governing mainline baseline, the workstream still needs one fresh post-rebase converge and end-to-end public verification run before it can be marked live-applied or carried onto `main`

## Verification Plan

- run the LiveKit unit and topology tests
- run the repository validation gates required by `agent-standards` plus the LiveKit syntax and data-model checks
- run the branch-local LiveKit converge and verification path while the protected integration surfaces remain deferred
- after merge-to-main, rerun the governed `live-apply-service` path with the documented ADR 0191 in-place mutation exception so the exact-main replay clears `check-canonical-truth`
- capture guest-local listener proof, public room-lifecycle proof, and the resulting live-apply receipt
