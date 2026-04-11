# Workstream ws-0257-main-merge

- ADR: [ADR 0257](../adr/0257-openclaw-compatible-skill-md-packs-and-workspace-precedence-for-serverclaw.md)
- Title: Integrate ADR 0257 exact-main replay onto `origin/main`
- Status: `merged`
- Included In Repo Version: 0.177.117
- Platform Version Observed During Merge: 0.130.76
- Release Date: 2026-03-31
- Branch: `codex/ws-0257-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0257-main-merge`
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

- Release `0.177.117` carries ADR 0257's exact-main replay onto merged mainline
  truth.
- The integrated platform baseline advanced from `0.130.75` to `0.130.76`
  after the exact-main replay and verification completed.
- `versions/stack.yaml` now points `serverclaw_skills` at
  `2026-03-31-adr-0257-serverclaw-skill-packs-mainline-live-apply`, while ADR
  0257 itself records `0.177.117` / `0.130.76` as the first merged repo and
  platform versions where the decision became true.
- `README.md`, `RELEASE.md`, `changelog.md`, `docs/release-notes/`,
  `versions/stack.yaml`, and `build/platform-manifest.json` were all refreshed
  from this merged baseline during the same integration step.
