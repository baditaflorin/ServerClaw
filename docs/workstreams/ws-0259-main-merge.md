# Workstream ws-0259-main-merge

- ADR: [ADR 0259](../adr/0259-n8n-as-the-external-app-connector-fabric-for-serverclaw.md)
- Title: Integrate ADR 0259 exact-main replay onto `origin/main`
- Status: `merged`
- Included In Repo Version: 0.177.79
- Platform Version Observed During Merge: 0.130.54
- Release Date: 2026-03-29
- Branch: `codex/ws-0259-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0259-main-integration`
- Owner: codex
- Depends On: `ws-0259-live-apply`

## Purpose

Carry the verified ADR 0259 exact-main replay onto the current `origin/main`,
refresh the protected canonical-truth and generated status surfaces from that
merged baseline, and publish the latest n8n connector-fabric receipt without
changing ADR 0259's original first-implementation truth.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0259-main-merge.md`
- `docs/workstreams/ws-0259-live-apply.md`
- `docs/adr/0259-n8n-as-the-external-app-connector-fabric-for-serverclaw.md`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.79.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `receipts/live-applies/2026-03-29-adr-0259-n8n-serverclaw-connector-fabric-mainline-live-apply.json`

## Verification

- Release `0.177.79` was cut from the merged integration worktree after `git merge --no-ff codex/adr-0259-live-apply`, and the protected release surfaces now carry ADR 0259 on top of `origin/main` commit `4a1f518ab7b0f7e5a997110f55c683a6700c1667`.
- `make converge-n8n` succeeded from source commit `c54fe1c579551248792f064e4e281d00aebf6bd0` with `docker-runtime-lv3 ok=117 changed=2 failed=0 skipped=32`, `postgres-lv3 ok=47 changed=0 failed=0 skipped=7`, `nginx-lv3 ok=37 changed=2 failed=0 skipped=8`, and `localhost ok=18 changed=0 failed=0 skipped=3`.
- Public edge verification returned `{"status":"ok"}` from `https://n8n.lv3.org/healthz`, `HTTP/2 302` from `https://n8n.lv3.org/`, and `HTTP/2 404` without an oauth redirect from `https://n8n.lv3.org/webhook-test/serverclaw-connector-smoke`.
- Guest-local verification on `docker-runtime-lv3` returned `readiness_status: 200`, `readiness_body: ok`, `login_email: ops@lv3.org`, and `login_role: global:owner`, while `sudo docker ps | grep -w n8n` showed `docker.n8n.io/n8nio/n8n:2.2.6` and `openbao/openbao:2.5.1` both running.
- `uvx --from pyyaml python scripts/interface_contracts.py --check-live-apply service:n8n`, `uv run --with pyyaml python scripts/standby_capacity.py --service n8n`, `uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --check-live-apply --service n8n`, and `uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --check-live-apply --service n8n --allow-in-place-mutation` all passed from the integration worktree.

## Outcome

- Release `0.177.79` carries ADR 0259's exact-main replay onto `main`.
- The integrated platform baseline advanced from `0.130.53` to `0.130.54` after the exact-main replay and verification completed.
- `versions/stack.yaml` now points `n8n` at `2026-03-29-adr-0259-n8n-serverclaw-connector-fabric-mainline-live-apply` while ADR 0259 itself still records `0.130.50` as the first platform version where the decision became true.
