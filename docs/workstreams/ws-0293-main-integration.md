# Workstream ws-0293-main-integration

- ADR: [ADR 0293](../adr/0293-livekit-as-the-real-time-audio-and-voice-channel-for-agents.md)
- Title: Integrate ADR 0293 exact-main LiveKit replay onto `origin/main`
- Status: merged
- Included In Repo Version: 0.177.132
- Platform Version Observed During Integration: 0.130.83
- Release Date: 2026-04-01
- Live Applied On: 2026-04-01
- Branch: `codex/ws-0293-main-integration-r1`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0293-main-integration-r1`
- Owner: codex
- Depends On: `ws-0293-livekit-live-apply`

## Purpose

Carry the verified LiveKit branch replay onto the latest realistic
`origin/main`, cut the protected release and canonical-truth surfaces for
repository version `0.177.132`, rerun the governed exact-main
`live-apply-service service=livekit env=production` path from committed
source, and record the first exact-main authority for the LiveKit publication
and public room-lifecycle contract.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0293-livekit-live-apply.md`
- `docs/workstreams/ws-0293-main-integration.md`
- `docs/adr/0293-livekit-as-the-real-time-audio-and-voice-channel-for-agents.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-livekit.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.132.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `receipts/live-applies/2026-04-01-adr-0293-livekit-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-04-01-ws-0293-livekit-mainline-*`

## Verification

- `git fetch origin --prune` confirmed `origin/main` remained at commit
  `4d3ef7d3a61931e0e18e9d74ad97d7511ecb2f7d` with repository version
  `0.177.131`, so the exact-main integration baseline stayed stable throughout
  the final merge pass.
- `uv run --with pyyaml python scripts/release_manager.py status`,
  `--dry-run --bump patch`, and `--bump patch` succeeded, cutting release
  `0.177.132` and refreshing `README.md`, `RELEASE.md`, `VERSION`,
  `changelog.md`, `docs/release-notes/0.177.132.md`,
  `docs/release-notes/README.md`, and the generated platform truth surfaces.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=livekit env=production`
  succeeded from exact-main source commit
  `9cad64c634f304bce0e8946529fd9386a67f317e` with final recap
  `proxmox-host ok=32 changed=0 failed=0 skipped=12`,
  `docker-runtime ok=184 changed=4 failed=0 skipped=59`,
  `nginx-edge ok=46 changed=5 failed=0 skipped=7`, and
  `localhost ok=19 changed=0 failed=0 skipped=7`.
- Independent controller-side checks after the exact-main replay returned
  `HTTP/2 200` for `https://livekit.example.com`, presented
  `subject=CN=livekit.example.com` with `DNS:livekit.example.com` in the SAN set, and
  passed the standalone `scripts/livekit_tool.py verify-room-lifecycle` probe.
- The final exact-main validation bundle is green on the merged tree:
  `79 passed` across the LiveKit-focused pytest slice,
  `./scripts/validate_repo.sh workstream-surfaces generated-docs agent-standards`,
  `uv run --with pyyaml python scripts/ansible_scope_runner.py validate`,
  `uv run --with pyyaml python scripts/live_apply_receipts.py --validate`,
  `uvx --from pyyaml python scripts/canonical_truth.py --check`,
  `git diff --check`, and
  `python3 scripts/run_gate_fallback.py --workspace . --status-file .local/validation-gate/ws-0293-mainline-clean-r3.json --source local-validate workstream-surfaces schema-validation generated-docs dependency-graph`;
  `validate_repo.sh` emitted only non-blocking advisory warnings about
  `.config-locations.yaml` and `.repo-structure.yaml`.
- The final authoritative receipt is
  `receipts/live-applies/2026-04-01-adr-0293-livekit-mainline-live-apply.json`,
  which advances `platform_version` to `0.130.83`.
