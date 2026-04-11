# Workstream ws-0246-live-apply: ADR 0246 Live Apply From Latest `origin/main`

- ADR: [ADR 0246](../adr/0246-startup-readiness-liveness-and-degraded-state-semantics.md)
- Title: Apply startup, readiness, liveness, and degraded-state semantics to the live runtime-assurance paths
- Status: live_applied
- Implemented In Repo Version: 0.177.60
- Live Applied In Platform Version: 0.130.44
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0246-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0246-live-apply`
- Owner: codex
- Depends On: `adr-0064-health-probe-contracts`, `adr-0123-service-uptime-contracts`, `adr-0244-runtime-assurance-matrix-per-service-and-environment`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0246-live-apply.md`, `docs/adr/0246-startup-readiness-liveness-and-degraded-state-semantics.md`, `docs/adr/.index.yaml`, `docs/runbooks/health-probe-contracts.md`, `docs/runbooks/service-uptime-contracts.md`, `docs/runbooks/scaffold-new-service.md`, `config/health-probe-catalog.json`, `playbooks/tasks/post-verify.yml`, `collections/ansible_collections/lv3/platform/playbooks/tasks/post-verify.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`, `platform/health/semantics.py`, `platform/health/composite.py`, `platform/graph/client.py`, `platform/world_state/workers.py`, `scripts/platform_observation_tool.py`, `scripts/scaffold_service.py`, `scripts/validate_repository_data_models.py`, `tests/test_post_verify_tasks.py`, `tests/test_platform_observation_tool.py`, `tests/test_world_state_workers.py`, `tests/test_health_composite.py`, `tests/test_scaffold_service.py`, `tests/unit/test_graph_client.py`

## Scope

- add one shared runtime-state classifier so startup, ready, degraded, and failed mean the same thing in the observation loop, world-state worker, and health composite
- extend the probe catalog and shared post-verify path to support optional `startup` probes without breaking existing services
- seed startup probes for services that already have a lighter liveness check and a deeper readiness contract
- replay the affected live services from this isolated worktree and record durable evidence without touching protected release files on the branch

## Verification Plan

- run focused pytest for the updated health semantics, observation, scaffold, and graph paths
- run repository validation slices for data models, health probes, agent standards, YAML/JSON shape, and Ansible syntax
- replay the live `converge-windmill` and `converge-api-gateway` paths from this worktree
- verify the live world-state `service_health` payload and the platform API health surface expose the new runtime-state semantics

## Live Apply Outcome

- rebased branch head `dc0624974fff094ff0f50a096ea5c411d64d53bf` re-ran the focused pytest slice with `36 passed in 2.25s`, and `./scripts/validate_repo.sh data-models health-probes agent-standards yaml json ansible-syntax workstream-surfaces` completed successfully
- the Windmill replay initially exposed a false failure in `Converge repo-managed Windmill schedule enabled flags`; after fixing the task's wrapper-output reporting and resuming from `Generate the Windmill superadmin secret`, the replay completed with `docker-runtime : ok=106 changed=21 failed=0 skipped=23`, and the seeded Windmill healthcheck assertions passed
- `make converge-api-gateway` completed successfully from the same worktree with `docker-runtime : ok=236 changed=106 failed=0 skipped=40`, including the shared startup, liveness, and readiness post-verify checks
- `uv run --with pyyaml python scripts/platform_observation_tool.py --checks check-service-health --output-dir .local/platform-observation/ws-0246-verify --digest-path .local/platform-observation/ws-0246-verify/digest.md` recorded `runtime_state=ready` plus structured `phase_results` for `api_gateway`, `platform_context_api`, and `windmill`; the broader estate still showed unrelated pre-existing `failed` and `startup` services outside ADR 0246 scope
- the latest host snapshot reported `proxmox-host`, kernel `6.17.13-2-pve`, and `pve-manager/9.1.6/71482d1833ded40a`, while authenticated `https://api.example.com/v1/platform/health/{api_gateway,platform_context_api,windmill}` checks all returned `status=healthy`, `safe_to_act=true`, and `health_probe=ready`

## Live Evidence

- live-apply receipt: `receipts/live-applies/2026-03-28-adr-0246-runtime-state-semantics-live-apply.json`
- live source commit: `dc0624974fff094ff0f50a096ea5c411d64d53bf`
- local observation artifact: `.local/platform-observation/ws-0246-verify/check-service-health.json`

## Mainline Integration Outcome

- merged to `main` in repository version `0.177.60`
- updated `VERSION`, `changelog.md`, `RELEASE.md`, `docs/release-notes/0.177.60.md`, `docs/release-notes/README.md`, `README.md`, `versions/stack.yaml`, `build/platform-manifest.json`, and `docs/diagrams/agent-coordination-map.excalidraw` only during the final mainline integration step
- preserved platform version `0.130.44` because the verified ADR 0246 live replay already ran on the current platform baseline, and the rebased `origin/main` additions from ADR 0242 and ADR 0253 had already been live-applied separately

## Merge-To-Main Notes

- remaining for merge to `main`: none
