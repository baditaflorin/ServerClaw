# Workstream ws-0252-main-merge

- ADR: [ADR 0252](../adr/0252-route-and-dns-publication-assertion-ledger.md)
- Title: Integrate ADR 0252 exact-main replay onto `origin/main`
- Status: `merged`
- Included In Repo Version: 0.177.76
- Platform Version Observed During Merge: 0.130.51
- Release Date: 2026-03-29
- Branch: `codex/ws-0252-main-merge-r3`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0252-main-merge-r3`
- Owner: codex
- Depends On: `ws-0252-mainline-replay`

## Purpose

Carry the verified ADR 0252 latest-main replay onto the current `origin/main`,
refresh the protected canonical-truth surfaces from that synchronized baseline,
and publish the latest route, edge, and private Vaultwarden evidence without
changing ADR 0252's original first-implementation truth.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0252-main-merge.md`
- `docs/workstreams/ws-0252-mainline-replay.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.76.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`

## Verification

- `scripts/validate_repo.sh workstream-surfaces agent-standards data-models` passed on the integration branch after registering `ws-0252-main-merge` and restoring `ws-0252-mainline-replay` to the repo's `live_applied` canonical-truth path.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the verified ADR 0252 exact-main replay while the current mainline platform baseline remains 0.130.51 and the new mainline receipt becomes canonical for the governed route, edge, and private Vaultwarden evidence" --released-on 2026-03-29 --dry-run` reported `Current version: 0.177.75`, `Next version: 0.177.76`, and `Unreleased notes: 1`.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the verified ADR 0252 exact-main replay while the current mainline platform baseline remains 0.130.51 and the new mainline receipt becomes canonical for the governed route, edge, and private Vaultwarden evidence" --released-on 2026-03-29` prepared release `0.177.76`.
- `make generate-platform-manifest` refreshed `build/platform-manifest.json`.
- `scripts/validate_repo.sh workstream-surfaces agent-standards json yaml shell data-models policy architecture-fitness generated-docs generated-portals` passed after regenerating `docs/site-generated/architecture/dependency-graph.md` and `docs/diagrams/agent-coordination-map.excalidraw`.

## Outcome

- Release `0.177.76` carries ADR 0252's exact-main replay onto `main`.
- The integrated platform baseline remains `0.130.51`; this integration does not bump the live platform version.
- `versions/stack.yaml` now points `public_edge_publication`, `route_dns_assertion_ledger`, and `vaultwarden` at `2026-03-29-adr-0252-route-and-dns-publication-assertion-ledger-mainline-live-apply`.
