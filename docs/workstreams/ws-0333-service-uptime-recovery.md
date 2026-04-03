# Workstream ws-0333-service-uptime-recovery: Fail Closed Before Runtime-Pool Retirement Or Shared-Runtime Recovery Can Take Down Legacy Services

- ADR: [ADR 0319](../adr/0319-runtime-pools-as-the-service-partition-boundary.md), [ADR 0320](../adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md)
- Title: Add fail-closed retirement gates for runtime-pool migrations after the April 3 shared-runtime outage
- Status: merged
- Implemented In Repo Version: 0.178.1
- Live Applied In Platform Version: N/A
- Implemented On: 2026-04-03
- Live Applied On: N/A
- Branch: `codex/ws-0333-service-uptime-recovery`
- Worktree: `.worktrees/ws-0333-service-uptime-recovery`
- Owner: codex
- Depends On: `ws-0325-service-uptime-investigation`, `ws-0330-runtime-pool-transition-program`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0333-service-uptime-recovery.md`, `playbooks/runtime-general-pool.yml`, `playbooks/runtime-control-pool.yml`, `playbooks/runtime-ai-pool.yml`, `docs/runbooks/configure-runtime-general-pool.md`, `docs/runbooks/configure-runtime-control-pool.md`, `docs/runbooks/configure-runtime-ai-pool.md`, `docs/runbooks/configure-keycloak.md`, `docs/runbooks/configure-openbao.md`, `collections/ansible_collections/lv3/platform/roles/common/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/common/meta/argument_specs.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_daemon_restart.yml`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/openbao_runtime/tasks/main.yml`, `docs/diagrams/agent-coordination-map.excalidraw`, `tests/test_common_docker_daemon_restart_helper.py`, `tests/test_keycloak_runtime_role.py`, `tests/test_openbao_runtime_role.py`, `tests/test_runtime_general_pool_playbook.py`, `tests/test_runtime_control_pool_playbook.py`, `tests/test_runtime_ai_pool_playbook.py`

## Why This Exists

The April 3 live runtime check found two conditions that can strand services
down even when the repo models the migration correctly on paper:

- `docker-runtime-lv3` still experienced host-wide Docker restarts during
  service-specific Ansible runs. The guest journal on `2026-04-03T06:34`
  recorded an active Keycloak converge stopping `docker.service` on the shared
  runtime and replaying bridge-chain recovery logic there.
- `runtime-general-lv3` and `runtime-control-lv3` are declared in repo
  metadata, but the corresponding live VMs `191` and `192` did not yet exist on
  the Proxmox host during this check. That means any retirement step that stops
  the legacy `docker-runtime-lv3` copies must fail closed until the destination
  pool has been verified in the same run.

## Scope

- gate the retirement plays in `playbooks/runtime-general-pool.yml`,
  `playbooks/runtime-control-pool.yml`, and `playbooks/runtime-ai-pool.yml`
  behind controller-local facts that are set only after the destination pool
  verification succeeds
- add a shared helper that refuses service-specific Docker daemon restarts on
  protected shared-runtime hosts unless an operator explicitly approves a
  maintenance-window override
- route the observed Keycloak and OpenBao bridge-chain recovery paths through
  that helper so the default converge path fails closed instead of restarting
  Docker on `docker-runtime-lv3`
- update the runtime-pool runbooks to warn operators not to bypass the new
  fail-closed retirement guard with retirement-only or limited-scope replays
- update the Keycloak and OpenBao runbooks so their stated recovery path matches
  the new shared-runtime Docker restart guard
- add regression coverage so future refactors cannot remove the guard silently

## Merged Outcome

- `runtime-general`, `runtime-control`, and `runtime-ai` retirement plays now
  assert destination readiness before any legacy shutdown path can run.
- shared-runtime Docker restarts now flow through a common helper that refuses
  to restart Docker on protected hosts unless an operator explicitly opts in.
- the observed Keycloak and OpenBao bridge-chain recovery paths now use that
  helper, so routine converges fail closed on `docker-runtime-lv3`.
- the April 3 outage pattern is now documented in the runtime-pool, Keycloak,
  and OpenBao runbooks plus the generated coordination map.

## Verification Plan

- run the runtime-pool playbook regression tests that assert the new
  controller-local readiness facts and retirement assertions
- run targeted Keycloak, OpenBao, and common-helper tests that assert the new
  shared-runtime Docker restart guard
- run `scripts/validate_repo.sh agent-standards workstream-surfaces` after the
  workstream registry update
- sanity-check the edited playbooks with `git diff --check`
