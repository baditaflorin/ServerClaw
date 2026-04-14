# Workstream ws-0370-live-apply: ADR 0370 Shared Lifecycle Includes

- ADR: [ADR 0370](../adr/0370-service-lifecycle-task-includes.md)
- Title: complete ADR 0370 shared lifecycle adoption and live-apply it from latest `origin/main`
- Status: live_applied
- Included In Repo Version: `0.178.141`
- Included In Platform Version: `0.178.141`
- Branch-Local Receipt: `receipts/live-applies/2026-04-14-adr-0370-service-lifecycle-task-includes-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-14-adr-0370-service-lifecycle-task-includes-mainline-live-apply.json`
- Implemented On: 2026-04-14
- Latest Verified Base: `origin/main@3cb78f677e3ed6b0f3343c86085c405fdecac8d9` (`repo 0.178.140`, `platform 0.178.138`)
- Branch: `codex/ws-0370-exact-main`
- Worktree: removed after merge-to-main
- Owner: codex
- Depends On: `ADR 0021`, `ADR 0063`, `ADR 0165`, `ADR 0370`, `ADR 0371`
- Conflicts With: none

## Scope

- finish the remaining runtime-role adoption of ADR 0370's shared lifecycle helpers, especially the `docker_compose_converge` and remote OpenBao helper paths
- preserve fresh-worktree `.local` identity overlay materialization so exact-main replays use the real private-domain runtime values instead of committed `example.com` placeholders
- verify the repo automation surfaces touched by the migration, including workstream, validation, and receipt tooling
- perform the exact-main live apply and record merge-safe evidence for both the branch-local and integrated-mainline replays

## Outcome

- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_compose_env.yml` now accepts controller-local artifact roots and a configurable remote OpenBao API URL, which lets fresh worktrees derive the real deployment domain from `.local/identity.yml` instead of replaying `example.com` placeholders.
- `collections/ansible_collections/lv3/platform/roles/livekit_runtime/tasks/main.yml` and `playbooks/livekit.yml` now converge LiveKit on `runtime-comms`, use the runtime-control OpenBao endpoint, and preserve the governed service-lifecycle helper path during exact-main replay.
- `inventory/group_vars/all/platform_services.yml`, `inventory/host_vars/proxmox-host.yml`, and generated `inventory/group_vars/platform.yml` now agree that LiveKit's edge publication and Proxmox TCP/UDP forwarding terminate on `runtime-comms` rather than `docker-runtime`.
- Protected integration files were updated only in this closeout step: `VERSION`, `RELEASE.md`, `docs/release-notes/0.178.141.md`, `README.md`, `versions/stack.yaml`, the archived ws-0370 registry entry, and the live-apply receipts now all align to repo and platform version `0.178.141`.

## Verification

- Focused regression coverage passed on the exact-main candidate:
  `pytest -q tests/test_openbao_compose_env_helper.py tests/test_compose_runtime_secret_injection.py tests/test_livekit_runtime_role.py`
  returned `20 passed in 0.22s`; evidence:
  `receipts/live-applies/evidence/2026-04-14-ws-0370-mainline-pytest-r1-0.178.141.txt`.
- LiveKit playbook syntax validation passed via `make syntax-check-livekit`; evidence:
  `receipts/live-applies/evidence/2026-04-14-ws-0370-mainline-syntax-livekit-r1-0.178.141.txt`.
- `make generate-platform-vars` passed from the fresh worktree and regenerated `inventory/group_vars/platform.yml` plus the cross-cutting artifacts with the real `.local` overlay applied; evidence:
  `receipts/live-applies/evidence/2026-04-14-ws-0370-mainline-generate-platform-vars-r2-0.178.141.txt`.
- The final integrated validation bundle passed with the direct repo gates, live-apply receipt schema validation, `git diff --check`, `check-build-server`, and `make remote-validate`; evidence is recorded under the matching `2026-04-14-ws-0370-mainline-final-*.txt` files in `receipts/live-applies/evidence/`.

## Live Apply

- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=livekit env=production`
  completed on the exact-main candidate from latest `origin/main`, with public room lifecycle verification succeeding from the controller and the replay recorded in
  `receipts/live-applies/evidence/2026-04-14-ws-0370-mainline-livekit-live-apply-r2-0.178.141.txt`.
- The live replay exercised the repaired runtime-comms placement, the remote OpenBao helper path, nginx publication, and the Proxmox TCP/UDP forwarding contract for ports `7881` and `7882`.
- ADR 0370 now truthfully records `Implementation Status: Live applied`,
  `Implemented In Repo Version: 0.178.141`, `Implemented In Platform Version:
  0.178.141`, and `Implemented On: 2026-04-14`.

## Integration Notes

- The latest realistic base remained `origin/main@3cb78f677e3ed6b0f3343c86085c405fdecac8d9`
  while this closeout ran, so the integrated release bump was cut from that
  verified mainline state.
- The worktree-local replay initially exposed a fresh-worktree bug where generated
  files fell back to committed `example.com` placeholders. Regenerating platform
  vars from the `.local` overlay restored the real domain and IP topology without
  reintroducing deployment-specific values into generic committed source files.
- The verified workstream branch was promoted to `origin/main`, after which the
  temporary `.worktrees/ws-0370-exact-main` integration worktree was removed.
