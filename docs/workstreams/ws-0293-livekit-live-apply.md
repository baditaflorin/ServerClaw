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
- Shared Surfaces: `docs/adr/0293`, `docs/workstreams/ws-0293-livekit-live-apply.md`, `docs/runbooks/configure-livekit.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `playbooks/livekit.yml`, `playbooks/services/livekit.yml`, `collections/ansible_collections/lv3/platform/roles/livekit_runtime/`, `collections/ansible_collections/lv3/platform/roles/proxmox_network/`, `config/*livekit-related catalogs*`, `config/dependency-wave-playbooks.yaml`, `build/platform-manifest.json`, `receipts/image-scans/`, `receipts/live-applies/`

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
- `2026-03-31-ws-0293-livekit-branch-edge-public-verify-r4.txt` is the full post-rebase replay from commit `156fe7c35979c89fb425d70b40b2c074ffd05c48`; it successfully replayed Proxmox ingress, guest-local Docker and LiveKit convergence, guest-local listener checks, guest-local room lifecycle verification, and the shared NGINX publication, then failed only at the final controller-side public room-lifecycle probe after the public edge flipped back to a hostname-mismatched certificate during the retry window
- direct diagnostics during the same `r4` window showed `docker-runtime-lv3` still listening on `*:7880` and `*:7881`, successful guest-local access to `http://127.0.0.1:7880/twirp/livekit.RoomService/ListRooms`, and the branch inventory still declaring the expected `nginx-lv3 -> 7880` plus public `7881/7882` firewall rules, while the live nftables input chain on `docker-runtime-lv3` no longer contained those LiveKit ingress rules and `nginx-lv3` timed out reaching `10.10.10.20:7880`; that combination points to concurrent shared-host clobber rather than a remaining branch-side LiveKit runtime defect
- as of `2026-03-31T06:07:56Z`, this worktree reacquired broad ADR 0153 locks on `vm:110` and `host:proxmox_florin` and refreshed the narrower LiveKit locks; `vm:120` is still blocked by `agent:codex/ws-0290-live-apply` holding `vm:120/service:redpanda` through `2026-03-31T08:03:44Z`, so the next clean replay window cannot start until that parent VM lock clears
- commit `cb8780fd30ea444239d64914d2eab444d1e22ccd` also fixes `make converge-livekit` so it now forwards both `$(ANSIBLE_TRACE_ARGS)` and `$(EXTRA_ARGS)` to the playbook invocation; this was validated with `HETZNER_DNS_API_TOKEN=dummy make -n converge-livekit env=production EXTRA_ARGS='--limit localhost,nginx-lv3'` and `uv run --with pytest python -m pytest -q tests/test_livekit_playbook.py tests/test_livekit_runtime_role.py`
- the `r6` replay reached the final controller-side public room-lifecycle verification only after reapplying the missing `nginx-lv3 -> 7880` plus public `7881/7882` guest-firewall allowances from commit `f41d66406b6bca2b1af567d39006d1e347ff6fc7`; the corresponding direct probe from `nginx-lv3` to `10.10.10.20:7880` returned `401 Unauthorized`, proving the east-west signalling path was healthy before the runtime guest was clobbered again
- while `r6` was waiting on the controller-side public verify, concurrent sibling workstreams on `vm:120` replaced the live guest state: `/opt/lv3/livekit` disappeared, no LiveKit listeners remained on `7880/7881/7882`, and the live nftables input chain again lacked the LiveKit ingress rules even though the branch inventory still declared them; `2026-03-31-ws-0293-livekit-parent-lock-blocker-r7.txt` captures the resulting parent lock conflict and the missing runtime state
- commit `511866f40949acee078ba29d453769f3a919e3db` hardens the repo automation after that discovery by teaching both `playbooks/livekit.yml` and `playbooks/services/livekit.yml` to advertise and lock the full shared surfaces they really mutate: `host:proxmox_florin`, `host:proxmox_florin/service:proxmox_network`, `vm:110`, `vm:110/service:nginx_edge_publication`, `vm:120`, and `vm:120/service:livekit`
- the lock-model fix was validated with `uv run --with pytest --with pyyaml python -m pytest -q tests/test_livekit_playbook.py tests/test_ansible_execution_scopes.py tests/test_dependency_wave_apply.py` (`18 passed`) plus `uv run --with pyyaml python scripts/ansible_scope_runner.py validate`
- the latest realistic integration baseline is now `origin/main` commit `bd9f92ea90ee07df43caaafcf979701d4a9ccb41` at repo version `0.177.123`; once the parent `vm:120` lock clears, the remaining path is to replay LiveKit on this branch against that baseline, then fast-forward the final main-integration step onto the exact latest `origin/main`

## Verification Plan

- run the LiveKit unit and topology tests
- run the repository validation gates required by `agent-standards` plus the LiveKit syntax and data-model checks
- run the branch-local LiveKit converge and verification path while the protected integration surfaces remain deferred
- after merge-to-main, rerun the governed `live-apply-service` path with the documented ADR 0191 in-place mutation exception so the exact-main replay clears `check-canonical-truth`
- capture guest-local listener proof, public room-lifecycle proof, and the resulting live-apply receipt
