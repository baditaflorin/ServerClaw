# Workstream ws-0025-live-apply: Live Apply ADR 0025 From Latest `origin/main`

- ADR: [ADR 0025](../adr/0025-compose-managed-runtime-stacks.md)
- Title: Complete the host-managed compose stack lifecycle contract, verify it live, and prove the repo automation paths from latest `origin/main`
- Status: live_applied
- Branch: `codex/ws-0025-live-apply-r2`
- Worktree: deleted after live-apply closeout (original path `.worktrees/ws-0025-live-apply-r2`)
- Owner: codex
- Depends On: `adr-0025-compose-managed-runtime-stacks`, `adr-0373-service-registry-and-derived-defaults`, `adr-0168-automated-enforcement-of-agent-standards`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `workstreams/archive/2026/ws-0025-live-apply.yaml`, `docs/workstreams/ws-0025-live-apply.md`, `docs/adr/0025-compose-managed-runtime-stacks.md`, `docs/adr/0025-implementation-roadmap.md`, `docs/adr/implementation-status/adr-0025.md`, `docs/adr/implementation-status/adr-0025.yaml`, `docs/runbooks/compose-runtime-resilience.md`, `docs/runbooks/configure-docker-runtime.md`, `collections/ansible_collections/lv3/platform/playbooks/docker-runtime.yml`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/`, `scripts/validate_repo.sh`, `tests/test_docker_runtime_role.py`, `receipts/live-applies/`

## Scope

- add a repo-managed systemd lifecycle for compose stacks on hosts that use the shared `lv3.platform.docker_runtime` baseline
- keep the lifecycle contract driven by `platform_service_registry` so new compose services inherit it without bespoke per-role wiring
- verify the live platform picks up the managed units and that repo validation catches lifecycle-contract drift
- reconcile ADR 0025 metadata, implementation-status tracking, and branch-local evidence with the verified live state

## Non-Goals

- bumping `VERSION` on this workstream branch
- editing numbered release sections in `changelog.md` on this workstream branch
- updating the top-level integrated `README.md` summary on this workstream branch
- updating `versions/stack.yaml` unless this work becomes the final exact-main integration step
- refactoring every compose service role to stop using direct `docker compose` converge commands in the same branch

## Expected Repo Surfaces

- `workstreams.yaml`
- `workstreams/archive/2026/ws-0025-live-apply.yaml`
- `docs/workstreams/ws-0025-live-apply.md`
- `docs/adr/0025-compose-managed-runtime-stacks.md`
- `docs/adr/0025-implementation-roadmap.md`
- `docs/adr/implementation-status/adr-0025.md`
- `docs/adr/implementation-status/adr-0025.yaml`
- `docs/runbooks/compose-runtime-resilience.md`
- `docs/runbooks/configure-docker-runtime.md`
- `collections/ansible_collections/lv3/platform/playbooks/docker-runtime.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/`
- `scripts/validate_repo.sh`
- `tests/test_docker_runtime_role.py`
- `receipts/live-applies/`

## Expected Live Surfaces

- repo-managed `lv3-<service>.service` units exist for compose services on Docker hosts and are enabled on boot
- Docker hosts with existing compose stacks can be managed through `systemctl start|restart|stop lv3-<service>.service`
- the live apply leaves structured evidence showing the managed units, active states, and representative stack checks

## Verification

- `receipts/live-applies/evidence/2026-04-12-ws-0025-compose-stack-lifecycle-live-apply-r12-docker-runtime-converge.txt` removed conflicting host MTAs on `docker-runtime`, enabled the new compose lifecycle units, and exposed the remaining stale `woodpecker` host drift that blocked the first replay.
- `receipts/live-applies/evidence/2026-04-12-ws-0025-compose-stack-lifecycle-live-apply-r18-woodpecker-runtime-repair-playbook.txt` repaired the stale `woodpecker` compose file, removed the obsolete external Gitea network reference, reconciled the stack with `docker compose up -d --remove-orphans`, and restored `lv3-woodpecker.service` to an active state.
- `receipts/live-applies/evidence/2026-04-12-ws-0025-compose-stack-lifecycle-live-apply-r19-compose-stack-lifecycle-production.txt` completed the production multi-host replay across `artifact-cache`, `coolify`, `docker-runtime`, `runtime-ai`, `runtime-control`, and `runtime-general` with `failed=0` for every host.
- `receipts/live-applies/evidence/2026-04-12-ws-0025-mainline-compose-stack-lifecycle-live-apply-r1-0.178.126.txt` replayed the governed `make live-apply-service service=compose-stack-lifecycle env=production` wrapper from `main`, completed the Ansible recap with `failed=0` across all six Docker hosts, and showed only the shared ADR 0302 restic probe timeout after the replay itself succeeded.
- `receipts/live-applies/evidence/2026-04-12-ws-0025-mainline-compose-stack-host-verification-r1.txt` confirmed the repo-managed `lv3-*.service` lifecycle footprint on the targeted hosts and explicitly verified `lv3-mail-platform.service`, `lv3-woodpecker.service`, and `lv3-rag-context.service` as `enabled` and `active` on `docker-runtime`.
- `receipts/live-applies/evidence/2026-04-12-ws-0025-mainline-restic-trigger-status-r1.txt` preserved the exact post-apply timeout transcript for the governed restic probe (`restic snapshots --json` timed out after 180 seconds) so the remaining ADR 0302 follow-up is visible without hiding the successful compose lifecycle replay.

## Closeout Notes

- ws-0025 is fully merged and live-applied from `main`; the remaining non-green evidence is the shared ADR 0302 restic snapshot probe timeout after the successful replay, which does not change the verified ADR 0025 platform state.
- The committed receipt for this workstream is `receipts/live-applies/2026-04-12-ws-0025-compose-stack-lifecycle-mainline-live-apply.json`, and `versions/stack.yaml` should treat it as the latest receipt for `docker_runtime`, `mail_platform`, and `woodpecker`.
