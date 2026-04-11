# Workstream ws-0256-live-apply: ADR 0256 Live Apply From Latest `origin/main`

- ADR: [ADR 0256](../adr/0256-mautrix-bridges-for-external-chat-channel-adapters.md)
- Title: Matrix mautrix bridge live apply from latest `origin/main`
- Status: `live_applied`
- Implemented In Repo Version: 0.177.98
- Live Applied In Platform Version: 0.130.65
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0256-mainline-refresh`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0256-mainline-refresh`
- Owner: codex
- Depends On: `ws-0255-live-apply`, `adr-0023-docker-runtime-vm-baseline`, `adr-0026-dedicated-postgresql-vm-baseline`, `adr-0077-compose-runtime-secrets-injection`, `adr-0255-matrix-synapse-as-the-canonical-serverclaw-conversation-hub`
- Conflicts With: none

## Purpose

Implement ADR 0256 on top of the already-live Matrix Synapse service by adding
repo-managed mautrix Discord and WhatsApp bridges, bridge-local secrets and
database automation, and branch-local live-apply evidence that can later be
merged onto the protected mainline surfaces safely.

## Latest Realistic Bridge Versions

- On 2026-03-30, the selected stable Discord bridge image is
  `dock.mau.dev/mautrix/discord:v0.7.6@sha256:e4946b0df6a2786c88ed490e0d2692e352f1b79b9ff0e821a33764bd8bd1fffd`.
- On 2026-03-30, the selected stable WhatsApp bridge image is
  `dock.mau.dev/mautrix/whatsapp:v0.2603.0@sha256:b49009312361d9ea0d7090716fd09f2323f477b32bd119648c6ca2d558a3e236`.
- Floating `latest` tags were intentionally not selected because they are
  moving commit-build aliases rather than the latest realistic stable releases.

## Planned Verification

- focused pytest coverage for the Matrix playbook plus runtime and postgres
  roles
- `make syntax-check-matrix-synapse`
- `./scripts/validate_repo.sh agent-standards`
- `python scripts/validate_repository_data_models.py --validate`
- full `make converge-matrix-synapse` live apply against the current platform
- public and controller Matrix client-version checks, bridge container-health
  checks, and `scripts/matrix_bridge_smoke.py` management-room verification

## Verification

- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest -q tests/test_matrix_synapse_playbook.py tests/test_matrix_synapse_postgres_role.py tests/test_matrix_synapse_runtime_role.py` passed
- `make syntax-check-matrix-synapse` passed after the live-apply fixes landed
- `python3 -m py_compile scripts/matrix_admin_register.py scripts/matrix_bridge_smoke.py` passed after the public verification helper fixes landed
- `python3 scripts/container_image_policy.py --validate` passed
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate` passed
- `./scripts/validate_repo.sh agent-standards` passed on the workstream tree
- `make preflight WORKFLOW=converge-matrix-synapse` passed
- `make converge-matrix-synapse` passed on 2026-03-30 and re-verified the public management-room smoke from the governed playbook

## Live Apply Outcome

- the branch-local live apply now converges Synapse plus both repo-managed mautrix bridges end to end on `docker-runtime`
- `https://matrix.example.com/_matrix/client/versions` returns `HTTP/2 200`, the private controller path `http://100.64.0.1:8015/_matrix/client/versions` returns `HTTP/1.1 200 OK`, and the public smoke helper now receives bridge replies from both `@discordbot:matrix.example.com` and `@whatsappbot:matrix.example.com`
- the live replay exposed and fixed four real defects before the successful converge: stale Docker network recovery on the shared runtime guest, bridge registration file permissions for Synapse, unreliable admin bootstrap handling when `register_new_matrix_user --exists-ok` returned non-zero for an existing user, and public verification helper bugs around the Matrix versions endpoint plus login-rate-limit handling
- the authoritative exact-main replay now passed from repo release `0.177.98`, so the Matrix bridge rollout is canonical on `main` and the platform version advances to `0.130.65`

## Live Evidence

- receipt: `receipts/live-applies/2026-03-30-adr-0256-mautrix-bridges-live-apply.json`
- canonical merged-main receipt: `receipts/live-applies/2026-03-30-adr-0256-mautrix-bridges-mainline-live-apply.json`
- successful branch-local converge log: `receipts/live-applies/evidence/2026-03-30-ws-0256-converge-matrix-synapse-r7.txt`
- successful merged-main converge log: `receipts/live-applies/evidence/2026-03-30-adr-0256-mainline-converge-matrix-synapse-0.177.98.txt`
- intermediate failure logs retained for auditability:
  `receipts/live-applies/evidence/2026-03-30-ws-0256-converge-matrix-synapse-r1.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0256-converge-matrix-synapse-r2.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0256-converge-matrix-synapse-r3.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0256-converge-matrix-synapse-r4.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0256-converge-matrix-synapse-r5.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0256-converge-matrix-synapse-r6.txt`

## Mainline Integration Resolution

- exact-main integration completed from repo version `0.177.98`, and the canonical platform version now advances to `0.130.65`
- before the exact-main replay, `origin/main` was re-fetched and confirmed to still be commit `7afd0b6e0798b93c475581ac316dd6e35c46514e`, so source commit `85d330315274610b7186a3a7f7763cb5fa312c90` represented the newest realistic mainline plus ADR 0256
- the canonical mainline receipt is `receipts/live-applies/2026-03-30-adr-0256-mautrix-bridges-mainline-live-apply.json`, and the exact-main replay transcript is preserved in `receipts/live-applies/evidence/2026-03-30-adr-0256-mainline-converge-matrix-synapse-0.177.98.txt`

## Mainline Guardrails

- Protected integration files (`VERSION`, release sections in `changelog.md`,
  `README.md` integrated status, and `versions/stack.yaml`) remain untouched in
  this branch until the final exact-main integration step.
- If branch-local live apply succeeds before the final main merge, the receipt
  and verification evidence must state exactly which protected files remain for
  merge-to-main.
