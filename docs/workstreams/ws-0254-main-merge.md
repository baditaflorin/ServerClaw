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
- `receipts/live-applies/2026-03-29-adr-0254-serverclaw-distinct-product-surface-mainline-live-apply.json`

## Verification

- `git fetch origin --prune` refreshed the integration worktree onto `origin/main` commit `8871117b40466b7907a33992f44ca7d83a3e9409`, and the protected release cut advanced the repository version from `0.177.83` to `0.177.84`.
- The synchronized exact-main source commit `54622948a39fa6632058b63536204188e5040753` replayed `make converge-serverclaw` successfully with recap `coolify-lv3 ok=58 changed=0 failed=0 skipped=16`, `docker-runtime-lv3 ok=63 changed=0 failed=0 skipped=7`, `nginx-lv3 ok=38 changed=2 failed=0 skipped=8`, and `proxmox_florin ok=229 changed=0 failed=0 skipped=111`.
- Post-replay platform checks confirmed `Debian-trixie-latest-amd64-base`, kernel `6.17.13-2-pve`, and `pve-manager/9.1.6/71482d1833ded40a` remained active on `proxmox_florin`, with `/etc/pve/firewall/170.fw` still containing `17:IN ACCEPT -source 10.10.10.10/32 -p tcp -dport 8096`.
- Internal path verification from `nginx-lv3` returned `Connection to 10.10.10.70 8096 port [tcp/*] succeeded!`, and `curl -sv --max-time 5 http://10.10.10.70:8096/ -o /dev/null` returned `HTTP/1.1 200 OK` from `uvicorn`.
- Guest-local verification on `coolify-lv3` returned JSON for `ops@lv3.org` with `role":"admin"` and a bearer token from `http://127.0.0.1:8096/api/v1/auths/signin`.
- Public edge verification returned `HTTP/1.1 308 Permanent Redirect` from `http://chat.lv3.org/` and `HTTP/2 200` from `https://chat.lv3.org/` after the exact-main replay.
- The repo automation and validation sweep for this merged state is recorded below after the integrated gate run completes.

## Outcome

- Release `0.177.84` now carries ADR 0254 onto `main` from the synchronized latest-main baseline.
- Platform version `0.130.58` is the first integrated platform version that records ADR 0254 as verified from the canonical mainline replay.
- The branch-local receipt remains preserved as the first latest-main candidate proof, and the canonical mainline receipt now supersedes it for integrated truth.
