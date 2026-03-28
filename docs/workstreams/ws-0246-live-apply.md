# Workstream ws-0246-live-apply: ADR 0246 Live Apply From Latest `origin/main`

- ADR: [ADR 0246](../adr/0246-startup-readiness-liveness-and-degraded-state-semantics.md)
- Title: Apply startup, readiness, liveness, and degraded-state semantics to the live runtime-assurance paths
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0246-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0246-live-apply`
- Owner: codex
- Depends On: `adr-0064-health-probe-contracts`, `adr-0123-service-uptime-contracts`, `adr-0244-runtime-assurance-matrix-per-service-and-environment`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0246-live-apply.md`, `docs/adr/0246-startup-readiness-liveness-and-degraded-state-semantics.md`, `docs/adr/.index.yaml`, `docs/runbooks/health-probe-contracts.md`, `docs/runbooks/service-uptime-contracts.md`, `docs/runbooks/scaffold-new-service.md`, `config/health-probe-catalog.json`, `playbooks/tasks/post-verify.yml`, `collections/ansible_collections/lv3/platform/playbooks/tasks/post-verify.yml`, `platform/health/semantics.py`, `platform/health/composite.py`, `platform/graph/client.py`, `platform/world_state/workers.py`, `scripts/platform_observation_tool.py`, `scripts/scaffold_service.py`, `scripts/validate_repository_data_models.py`, `tests/test_post_verify_tasks.py`, `tests/test_platform_observation_tool.py`, `tests/test_world_state_workers.py`, `tests/test_health_composite.py`, `tests/test_scaffold_service.py`, `tests/unit/test_graph_client.py`

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

## Merge-To-Main Reminder

- protected integration files remain deferred on this branch: `VERSION`, release sections in `changelog.md`, the top-level `README.md` integrated summary, and `versions/stack.yaml`
- once the live apply is verified, mainline integration still needs the release/version bump, changelog/release notes, README truth refresh, and canonical platform-version recording
