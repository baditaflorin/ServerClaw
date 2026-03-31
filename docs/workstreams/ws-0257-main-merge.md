# Workstream ws-0257-main-merge

- ADR: [ADR 0257](../adr/0257-openclaw-compatible-skill-md-packs-and-workspace-precedence-for-serverclaw.md)
- Title: Integrate ADR 0257 exact-main replay onto `origin/main`
- Status: `ready_for_merge`
- Branch: `codex/ws-0257-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0257-main-merge`
- Owner: codex
- Depends On: `ws-0257-live-apply`

## Purpose

Carry the verified ADR 0257 ServerClaw skill-pack contract onto the latest
`origin/main`, replay the Windmill and API gateway live applies from that exact
mainline source tree, and then refresh the protected canonical-truth surfaces
only after the integrated platform verification is complete.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0257-main-merge.md`
- `docs/workstreams/adr-0257-serverclaw-skill-packs-live-apply.md`
- `docs/adr/0257-openclaw-compatible-skill-md-packs-and-workspace-precedence-for-serverclaw.md`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `receipts/live-applies/`

## Verification

- fetched `origin/main` on 2026-03-31 and confirmed the current tip as
  `0b86b8ac4e2c868bab2b489ecff1e44a3913a10c` with repo version `0.177.116`
- the exact-main replay completed across all required live surfaces:
  `make converge-api-gateway`,
  `make converge-openbao`,
  `make converge-windmill`,
  and the adjacent `step-ca` health proof all passed from this worktree
- controller, governed tool registry, public API gateway, and seeded Windmill
  direct proofs all resolved the same governed skill set for workspace `ops`,
  including the workspace-local `platform-observe` override shadowing the
  bundled pack
- the only code hardening required to finish the replay was the new OpenBao
  transient-read retry contract now committed in source commit
  `808b924df84dd7fdfd3f3871b5cfe1225b6b22a4`
- focused repository validation also passed on the exact-main branch:
  `52 passed` across the ADR 0257 skill-pack slices, `19 passed` for the
  OpenBao role regression slice, `make syntax-check-windmill`,
  `make syntax-check-api-gateway`, `./scripts/validate_repo.sh agent-standards`,
  and `scripts/validate_repository_data_models.py --validate`

## Outcome

- the latest realistic `origin/main` replay is complete and this branch is now
  ready for final merge-to-`main`
- protected integration files intentionally still remain untouched on this
  branch: ADR metadata, `VERSION`, `changelog.md`, `README.md`,
  `docs/release-notes/`, `versions/stack.yaml`, and `build/platform-manifest.json`
  should be refreshed only during the final `main` integration step
- the branch carries durable live evidence in
  `receipts/live-applies/2026-03-31-adr-0257-serverclaw-skill-packs-mainline-live-apply.json`
  so the final merge step can promote the exact proof set without replay drift
