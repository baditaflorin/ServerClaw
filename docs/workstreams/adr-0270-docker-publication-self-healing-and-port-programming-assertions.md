# Workstream ADR 0270: Docker Publication Self-Healing And Port-Programming Assertions

- ADR: [ADR 0270](../adr/0270-docker-publication-self-healing-and-port-programming-assertions.md)
- Title: Add a shared Docker publication assurance helper, post-verify repair hook, and live apply for managed Docker guests
- Status: live_applied
- Implemented In Repo Version: 0.177.94
- Live Applied In Platform Version: 0.130.62
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0270-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/adr-0270-main-integration`
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
  loop, then replay the automation live on `docker-runtime` and
  `coolify`

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

- `docker-runtime` and `coolify` install
  `/usr/local/bin/lv3-docker-publication-assurance`
- managed Docker services with declared contracts fail closed when bridge
  networks, host-side bind addresses, or Docker publication chains are missing
- the dedicated ADR 0270 playbook can repair missing Docker publication state
  before the service readiness probe runs

## Verification Plan

- run focused pytest coverage for the helper, playbook wiring, role install,
  observation path, and shared post-verify tasks
- run `./scripts/validate_repo.sh workstream-surfaces agent-standards yaml json data-models ansible-syntax role-argument-specs health-probes generated-docs`
- replay `make converge-docker-publication-assurance env=production` from this
  isolated latest-main worktree
- verify the installed helper and direct publication checks on
  `docker-runtime` and `coolify`
- update the protected integration surfaces on the synchronized mainline
  integration worktree and capture the canonical exact-main receipt

## Results

- The shared Docker publication assurance helper now distinguishes live
  `NetworkSettings.Ports` state from configured `HostConfig.PortBindings`,
  retries after a Docker daemon restart when `docker compose up` dies with an
  EOF against the control socket, and force-resets stale compose projects when
  bridge, bind, or DNAT state is missing.
- The synchronized exact-main replay from commit
  `6bbe13b66c382d5521cc7b85cc070355558fc326` succeeded via
  `make converge-docker-publication-assurance env=production`, with final recap
  `coolify : ok=69 changed=5 unreachable=0 failed=0 skipped=3 rescued=0 ignored=0`
  and
  `docker-runtime : ok=115 changed=3 unreachable=0 failed=0 skipped=6 rescued=0 ignored=0`,
  captured in
  `receipts/live-applies/evidence/2026-03-30-adr-0270-mainline-docker-publication-assurance-rerun-7.txt`.
- Post-replay diagnostics still caught Harbor in the stale-publication signature
  where `HostConfig.PortBindings` existed but `NetworkSettings.Ports` and the
  live `8095` listener did not. A governed follow-up
  `make converge-harbor env=production` repaired that state on the same head
  with final recap
  `docker-runtime : ok=134 changed=7 unreachable=0 failed=0 skipped=21 rescued=0 ignored=0`
  and
  `nginx-edge : ok=39 changed=3 unreachable=0 failed=0 skipped=11 rescued=0 ignored=0`,
  captured in
  `receipts/live-applies/evidence/2026-03-30-adr-0270-mainline-converge-harbor-r2.txt`.
- The final merged-main targeted regression slice returned `101 passed in
  25.79s` for the Harbor, Keycloak, OpenBao, Docker publication, Docker
  runtime, observation, post-verify, Gotenberg, Nextcloud, and nginx-edge
  publication coverage set, captured in
  `receipts/live-applies/evidence/2026-03-30-adr-0270-mainline-targeted-pytests-r3.txt`.
- The merged-main repository validation path also passed from the final
  synchronized snapshot with
  `LV3_SNAPSHOT_BRANCH=main ./scripts/validate_repo.sh workstream-surfaces agent-standards yaml json data-models ansible-syntax role-argument-specs health-probes generated-docs`,
  captured in
  `receipts/live-applies/evidence/2026-03-30-adr-0270-mainline-validate-repo-r9.txt`.
- Final steady-state verification after the Harbor repair is captured in
  `receipts/live-applies/evidence/2026-03-30-adr-0270-mainline-direct-and-public-verification-r2.txt`,
  which shows `harbor_public=Pong`, `harbor_local=Pong`,
  `keycloak_public_issuer=https://sso.example.com/realms/lv3`,
  `keycloak_local_issuer=https://sso.example.com/realms/lv3`,
  OpenBao unsealed on loopback, Outline healthy locally and publicly, and
  Langfuse health plus sign-in reachability returning success.

## Merge Follow-Through

- exact-main replay, receipt capture, merged-main validation, and protected
  integration surface updates are complete
- the final integrated release cut for ADR 0270 is now `0.177.94` on top of
  the refreshed latest `origin/main` baseline
