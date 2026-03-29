# Workstream ADR 0270: Docker Publication Self-Healing And Port-Programming Assertions

- ADR: [ADR 0270](../adr/0270-docker-publication-self-healing-and-port-programming-assertions.md)
- Title: Add a shared Docker publication assurance helper, post-verify repair hook, and live apply for managed Docker guests
- Status: ready_for_merge
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: 0.130.60
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
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
- `docs/runbooks/configure-keycloak.md`
- `docs/runbooks/configure-openbao.md`
- `docs/adr/0270-docker-publication-self-healing-and-port-programming-assertions.md`
- `docs/workstreams/adr-0270-docker-publication-self-healing-and-port-programming-assertions.md`
- `docs/adr/.index.yaml`
- `workstreams.yaml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_compose_env.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_systemd_credentials.yml`
- `collections/ansible_collections/lv3/platform/roles/harbor_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/reconcile_repo_managed_users.yml`
- `tests/test_docker_publication_assurance.py`
- `tests/test_harbor_runtime_role.py`
- `tests/test_docker_publication_assurance_playbook.py`
- `tests/test_docker_runtime_role.py`
- `tests/test_keycloak_runtime_role.py`
- `tests/test_openbao_compose_env_helper.py`
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

## Results

- The shared Docker publication assurance helper now distinguishes live
  `NetworkSettings.Ports` state from configured `HostConfig.PortBindings`,
  resets stale compose networks when Docker reports missing bridge state, and
  retries after a Docker daemon restart when `docker compose up` dies with an
  EOF against the control socket.
- The final focused regression slice for the branch returned `29 passed in
  0.92s` for `tests/test_harbor_runtime_role.py`,
  `tests/test_keycloak_runtime_role.py`,
  `tests/test_openbao_compose_env_helper.py`, and
  `tests/test_docker_publication_assurance.py`, building on the earlier
  `66 passed` multi-file branch validation captured in
  `receipts/live-applies/evidence/2026-03-29-adr-0270-focused-pytest-post-final-fixes.txt`.
- The full `make converge-keycloak env=production` replay succeeded after the
  workstream split repo-managed Keycloak user reconciliation into a retryable
  include and taught the shared OpenBao secret-delivery helpers to
  force-recreate OpenBao when the loopback `127.0.0.1:8201` publication
  disappears.
- A late branch verification sweep caught Harbor regressing again with
  `registry.lv3.org` redirecting to `https://nginx.lv3.org/...` and
  `127.0.0.1:8095` down. The first repair replay exposed a real Harbor recovery
  bug where stale-container cleanup assumed Docker was already reachable after a
  compose reset; this workstream patched that task, retested it, and the final
  `make converge-harbor env=production` replay completed with
  `docker-runtime-lv3 : ok=126 changed=1 failed=0 skipped=26` and
  `nginx-lv3 : ok=38 changed=3 failed=0 skipped=11`.
- Final steady-state verification is captured in
  `receipts/live-applies/evidence/2026-03-29-adr-0270-final-branch-verification-post-harbor-repair.txt`,
  which shows `registry.lv3.org/api/v2.0/ping => 200`, Harbor local and host-IP
  `8095` pings returning `Pong`, and Keycloak/OpenBao loopback health returning
  `200`.

## Merge Follow-Through

- merge this workstream onto the exact latest `origin/main`
- update ADR 0270 metadata to `Implementation Status: Implemented`, record the
  first repo version and first live platform version, and regenerate
  `docs/adr/.index.yaml`
- cut the protected integration surfaces on `main` only:
  `VERSION`, `changelog.md`, `docs/release-notes/`, `README.md`, and
  `versions/stack.yaml`
- replay the merged mainline from the synchronized integration worktree,
  capture the canonical exact-main receipt, and then mark this workstream
  `live_applied` in `workstreams.yaml`
