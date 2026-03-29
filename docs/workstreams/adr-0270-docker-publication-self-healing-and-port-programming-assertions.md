# Workstream ADR 0270: Docker Publication Self-Healing And Port-Programming Assertions

- ADR: [ADR 0270](../adr/0270-docker-publication-self-healing-and-port-programming-assertions.md)
- Title: Add a shared Docker publication assurance helper, post-verify repair hook, and live apply for managed Docker guests
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0270-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/adr-0270-live-apply`
- Owner: codex
- Depends On: `adr-0023-docker-runtime-vm-baseline`, `adr-0036-live-apply-receipts-and-verification-evidence`, `adr-0246-startup-readiness-liveness-and-degraded-state-semantics`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/adr-0270-docker-publication-self-healing-and-port-programming-assertions.md`, `docs/adr/0270-docker-publication-self-healing-and-port-programming-assertions.md`, `docs/adr/.index.yaml`, `docs/runbooks/docker-publication-assurance.md`, `docs/runbooks/health-probe-contracts.md`, `docs/runbooks/playbook-execution-model.md`, `Makefile`, `config/health-probe-catalog.json`, `playbooks/docker-publication-assurance.yml`, `playbooks/tasks/post-verify.yml`, `playbooks/tasks/docker-publication-assert.yml`, `collections/ansible_collections/lv3/platform/playbooks/tasks/post-verify.yml`, `collections/ansible_collections/lv3/platform/playbooks/tasks/docker-publication-assert.yml`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/meta/argument_specs.yml`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/tasks/verify.yml`, `scripts/docker_publication_assurance.py`, `scripts/platform_observation_tool.py`, `scripts/validate_repository_data_models.py`, `tests/test_docker_publication_assurance.py`, `tests/test_docker_publication_assurance_playbook.py`, `tests/test_docker_runtime_role.py`, `tests/test_platform_observation_tool.py`, `tests/test_post_verify_tasks.py`, `receipts/live-applies/`

## Scope

- install one shared Docker publication assurance helper on every managed Docker
  guest instead of repeating ad hoc NAT-chain recovery logic inside individual
  service roles
- extend the health-probe catalog so the services with proven publication
  contracts declare their expected bridge networks, bind addresses, and port
  programming explicitly
- enforce the contract in both shared playbook post-verify and the observation
  loop, then replay the automation live on `docker-runtime-lv3` and
  `coolify-lv3`

## Expected Repo Surfaces

- `Makefile`
- `config/health-probe-catalog.json`
- `playbooks/docker-publication-assurance.yml`
- `playbooks/tasks/post-verify.yml`
- `playbooks/tasks/docker-publication-assert.yml`
- `collections/ansible_collections/lv3/platform/playbooks/tasks/post-verify.yml`
- `collections/ansible_collections/lv3/platform/playbooks/tasks/docker-publication-assert.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/meta/argument_specs.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/tasks/verify.yml`
- `scripts/docker_publication_assurance.py`
- `scripts/platform_observation_tool.py`
- `scripts/validate_repository_data_models.py`
- `docs/runbooks/docker-publication-assurance.md`
- `docs/runbooks/health-probe-contracts.md`
- `docs/runbooks/playbook-execution-model.md`
- `docs/adr/0270-docker-publication-self-healing-and-port-programming-assertions.md`
- `docs/workstreams/adr-0270-docker-publication-self-healing-and-port-programming-assertions.md`
- `docs/adr/.index.yaml`
- `workstreams.yaml`
- `tests/test_docker_publication_assurance.py`
- `tests/test_docker_publication_assurance_playbook.py`
- `tests/test_docker_runtime_role.py`
- `tests/test_platform_observation_tool.py`
- `tests/test_post_verify_tasks.py`
- `receipts/live-applies/`

## Expected Live Surfaces

- `docker-runtime-lv3` and `coolify-lv3` install
  `/usr/local/bin/lv3-docker-publication-assurance`
- managed Docker services with declared contracts fail closed when bridge
  networks, host-side bind addresses, or Docker publication chains are missing
- the dedicated ADR 0270 playbook can repair missing Docker publication state
  before the service readiness probe runs

## Verification Plan

- run focused pytest coverage for the helper, playbook wiring, role install,
  observation path, and shared post-verify tasks
- run `./scripts/validate_repo.sh agent-standards yaml json data-models ansible-syntax role-argument-specs health-probes`
- replay `make converge-docker-publication-assurance env=production` from this
  isolated latest-main worktree
- verify the installed helper and direct publication checks on
  `docker-runtime-lv3` and `coolify-lv3`
- record branch-local live-apply evidence and, if this branch becomes the final
  mainline integration candidate, update the protected release surfaces and
  exact-main receipt
