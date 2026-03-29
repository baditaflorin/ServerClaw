# Workstream ws-0254-main-merge

- ADR: [ADR 0254](../adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md)
- Title: Integrate ADR 0254 exact-main replay onto `origin/main`
- Status: `ready_for_merge`
- Included In Repo Version: 0.177.84
- Platform Version Observed During Merge: 0.130.58
- Release Date: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0254-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0254-main-merge`
- Owner: codex
- Depends On: `ws-0254-live-apply`

## Purpose

Carry the verified ADR 0254 latest-main replay onto the current `origin/main`,
refresh the protected release and canonical-truth surfaces from that merged
baseline, re-run the exact-main ServerClaw converge path from the integration
commit, and record the canonical mainline live-apply receipt before pushing
`origin/main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0254-main-merge.md`
- `docs/workstreams/ws-0254-live-apply.md`
- `docs/adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.84.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `config/check-runner-manifest.json`
- `config/validation-gate.json`
- `platform/policy/toolchain.py`
- `tests/test_policy_checks.py`
- `receipts/live-applies/2026-03-29-adr-0254-serverclaw-distinct-product-surface-mainline-live-apply.json`

## Verification

- `git fetch origin --prune` first refreshed the integration worktree onto `origin/main` commit `8871117b40466b7907a33992f44ca7d83a3e9409` for the release cut to `0.177.84`, then a later refresh merged the newer `origin/main` tip `430e364e2a810ccd6463e201fd8b7d41fed95676` into branch commit `39a7bd06302c7e5ab19a78d9a74a86377e09586d` before the final exact-main replay.
- The refreshed exact-main source commit `39a7bd06302c7e5ab19a78d9a74a86377e09586d` replayed `make converge-serverclaw` successfully with recap `coolify-lv3 ok=58 changed=0 failed=0 skipped=16`, `docker-runtime-lv3 ok=63 changed=0 failed=0 skipped=7`, `nginx-lv3 ok=39 changed=4 failed=0 skipped=7`, and `proxmox_florin ok=230 changed=3 failed=0 skipped=110`.
- Post-replay platform checks confirmed `Debian-trixie-latest-amd64-base`, kernel `6.17.13-2-pve`, and `pve-manager/9.1.6/71482d1833ded40a` remained active on `proxmox_florin`, with `/etc/pve/firewall/170.fw` still containing `17:IN ACCEPT -source 10.10.10.10/32 -p tcp -dport 8096`.
- Internal path verification from `nginx-lv3` returned `Connection to 10.10.10.70 8096 port [tcp/*] succeeded!`, and `curl -sv --max-time 5 http://10.10.10.70:8096/ -o /dev/null` returned `HTTP/1.1 200 OK` from `uvicorn`.
- Guest-local verification on `coolify-lv3` returned JSON for `ops@lv3.org` with `role":"admin"` and a bearer token from `http://127.0.0.1:8096/api/v1/auths/signin`.
- Public edge verification returned `HTTP/1.1 308 Permanent Redirect` from `http://chat.lv3.org/` and `HTTP/2 200` from `https://chat.lv3.org/` after the exact-main replay.
- `make validate` passed after regenerating `docs/diagrams/agent-coordination-map.excalidraw`, `docs/diagrams/service-dependency-graph.excalidraw`, and `build/platform-manifest.json` from the refreshed merge base.
- `make pre-push-gate` passed on the build-server at `2026-03-29T20:41:15.857152+00:00` with all blocking checks green, including `ansible-lint`, `ansible-syntax`, `schema-validation`, `policy-validation`, `generated-docs`, `generated-portals`, `security-scan`, and `integration-tests`.
- `make post-merge-gate` passed at `2026-03-29T20:56:38.536104+00:00` after making the cached ADR 0230 policy toolchain platform-aware in `platform/policy/toolchain.py` and raising the repo-wide `yaml-lint` gate timeout to `240` seconds for local amd64-container replays on arm64 hosts.
- `make gate-status` now reports both the last build-server gate run and the last Windmill post-merge gate run as `passed` on this worktree.

## Outcome

- Release `0.177.84` now carries ADR 0254 onto `main` from the synchronized latest-main baseline.
- Platform version `0.130.58` is the first integrated platform version that records ADR 0254 as verified from the canonical mainline replay.
- The branch-local receipt remains preserved as the first latest-main candidate proof, and the canonical mainline receipt now supersedes it for integrated truth.
- The repo automation path now reuses the correct policy binaries across mixed-architecture hosts and no longer drops the post-merge gate on the local `yaml-lint` timeout seen during the first replay attempt.
