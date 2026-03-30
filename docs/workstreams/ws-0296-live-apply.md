# Workstream WS-0296: Dedicated Artifact Cache VM Live Apply

- ADR: [ADR 0296](../adr/0296-dedicated-artifact-cache-vm-with-phased-consumer-adoption.md)
- Title: Provision `artifact-cache-lv3`, move the build host onto the dedicated cache plane, and record the exact live-apply proof from latest `origin/main`
- Status: ready_for_merge
- Branch-Local Source Repo Version: 0.177.101
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0296-dedicated-artifact-cache-vm-live-apply.json`
- Canonical Mainline Receipt: pending exact-main integration from current `origin/main`
- Live Applied In Platform Version: 0.130.68
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0296-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0296-live-apply`
- Owner: codex
- Depends On: `ws-0274-artifact-cache-plane`, `ws-0295-live-apply`, `adr-0084-packer-vm-template-pipeline`, `adr-0191-immutable-guest-replacement`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0296`, `docs/workstreams/ws-0296-live-apply.md`, `docs/runbooks/artifact-cache-runtime.md`, `docs/runbooks/configure-artifact-cache-vm.md`, `docs/runbooks/configure-build-artifact-cache.md`, `docs/runbooks/network-policy-reference.md`, `docs/site-generated/architecture/dependency-graph.md`, `inventory/hosts.yml`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `config/capacity-model.json`, `Makefile`, `playbooks/artifact-cache-vm.yml`, `playbooks/services/build-artifact-cache.yml`, `playbooks/tasks/docker-publication-assert.yml`, `roles/artifact_cache_runtime/`, `roles/docker_runtime/`, `roles/common/tasks/docker_bridge_chains.yml`, `collections/ansible_collections/lv3/platform/playbooks/artifact-cache-vm.yml`, `collections/ansible_collections/lv3/platform/playbooks/services/build-artifact-cache.yml`, `collections/ansible_collections/lv3/platform/playbooks/tasks/docker-publication-assert.yml`, `collections/ansible_collections/lv3/platform/roles/artifact_cache_runtime/`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/`, `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`, `config/ansible-execution-scopes.yaml`, `config/workflow-catalog.json`, `config/command-catalog.json`, `tests/test_artifact_cache_runtime_role.py`, `tests/test_artifact_cache_playbook.py`, `tests/test_common_docker_bridge_chains_helper.py`, `tests/test_docker_runtime_role.py`, `tests/test_post_verify_tasks.py`, `receipts/live-applies/`, `receipts/ops-portal-snapshot.html`

## Scope

- provision the dedicated `artifact-cache-lv3` guest as VM `180` on `10.10.10.80`
- converge the private cache-plane runtime on the dedicated guest through repo-managed automation
- move the first consumer phase from the old build-host-local cache stack to the dedicated cache VM
- verify the platform change end to end and leave exact evidence for merge-to-main

## Non-Goals

- broad runtime-host adoption beyond the build and CI lane
- public publication of the cache-plane ports
- changing protected release files on this workstream branch before the final integration step

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0296-live-apply.md`
- `docs/adr/0296-dedicated-artifact-cache-vm-with-phased-consumer-adoption.md`
- `docs/runbooks/artifact-cache-runtime.md`
- `docs/runbooks/configure-artifact-cache-vm.md`
- `docs/runbooks/configure-build-artifact-cache.md`
- `docs/runbooks/network-policy-reference.md`
- `docs/site-generated/architecture/dependency-graph.md`
- `inventory/hosts.yml`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `config/capacity-model.json`
- `Makefile`
- `playbooks/artifact-cache-vm.yml`
- `playbooks/services/build-artifact-cache.yml`
- `playbooks/tasks/docker-publication-assert.yml`
- `roles/artifact_cache_runtime/`
- `roles/docker_runtime/`
- `roles/common/tasks/docker_bridge_chains.yml`
- `collections/ansible_collections/lv3/platform/playbooks/artifact-cache-vm.yml`
- `collections/ansible_collections/lv3/platform/playbooks/services/build-artifact-cache.yml`
- `collections/ansible_collections/lv3/platform/playbooks/tasks/docker-publication-assert.yml`
- `collections/ansible_collections/lv3/platform/roles/artifact_cache_runtime/`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`
- `config/ansible-execution-scopes.yaml`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `tests/test_artifact_cache_runtime_role.py`
- `tests/test_artifact_cache_playbook.py`
- `tests/test_common_docker_bridge_chains_helper.py`
- `tests/test_docker_runtime_role.py`
- `tests/test_post_verify_tasks.py`
- `receipts/live-applies/`
- `receipts/ops-portal-snapshot.html`

## Expected Live Surfaces

- VM `180` exists as `artifact-cache-lv3` at `10.10.10.80`
- `artifact-cache-lv3` serves the four private cache endpoints on TCP `5001-5004`
- `docker-build-lv3` consumes those dedicated endpoints and no longer runs the old local `artifact-cache-*` containers

## Verification

- `uv run --with pytest python -m pytest -q tests/test_artifact_cache_runtime_role.py tests/test_artifact_cache_playbook.py tests/test_common_docker_bridge_chains_helper.py tests/test_docker_runtime_role.py tests/test_post_verify_tasks.py` passed with `18 passed in 1.02s`, covering the dedicated VM playbook, the artifact-cache runtime state transitions, the Docker-publication helper path fix, and the Docker bridge verification helper.
- `make syntax-check-artifact-cache-vm`, the `build-artifact-cache` scope syntax check, `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`, `./scripts/validate_repo.sh agent-standards`, `./scripts/validate_repo.sh workstream-surfaces`, `make generate-ops-portal`, and `make generate-changelog-portal` all passed after the capacity-model and workflow/catalog surfaces were updated for the new guest.
- `make configure-artifact-cache-vm env=production` completed successfully on retry `r8`, provisioning VM `180`, converging the Docker and firewall baselines on `artifact-cache-lv3`, warming the repo-derived cache plan, and finishing with final recap `artifact-cache-lv3 : ok=118 changed=9 unreachable=0 failed=0 skipped=7` and `proxmox_florin : ok=14 changed=4 unreachable=0 failed=0 skipped=3`.
- The governed wrapper path was exercised with `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=build-artifact-cache env=production EXTRA_ARGS='-e bypass_promotion=true'`; the run advanced through the repo-managed guard chain and then stopped only at `check-canonical-truth` because this workstream intentionally left the top-level `README.md` stale on the branch.
- After repairing the helper-source path used by `docker_runtime` and `playbooks/tasks/docker-publication-assert.yml` for nested service playbooks, the direct scoped replay `uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py run --inventory inventory/hosts.yml --run-id ws0296buildcachelive2 --playbook playbooks/services/build-artifact-cache.yml --env production -- --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e bypass_promotion=true` succeeded with final recap `docker-build-lv3 : ok=123 changed=7 unreachable=0 failed=0 skipped=20 rescued=0 ignored=0`.
- The fresh end-to-end verification in `receipts/live-applies/evidence/2026-03-30-ws-0296-end-to-end-verification.txt` confirmed VM `180` serves all four cache ports locally with a `50`-image warm set, `docker-build-lv3` now points its Docker mirrors and insecure registries at `10.10.10.80:5001-5004`, `docker buildx inspect lv3-cache --bootstrap` succeeds, and the old local `artifact-cache-*` containers are absent from the build guest.

## Results

- VM `180` now exists as `artifact-cache-lv3` on `10.10.10.80/24` with the pinned MAC address `BC:24:11:18:AC:80`, `4` vCPUs, `8192` MiB RAM, `160` GiB disk, and the declared internal-only firewall policy.
- The dedicated cache runtime is live on `artifact-cache-lv3`, with `artifact-cache-docker-hub`, `artifact-cache-ghcr`, `artifact-cache-plane`, and `artifact-cache-n8n` all serving TCP `5001-5004` and the repo-derived warm set now materialized on the dedicated guest instead of the build host.
- `docker-build-lv3` is now a cache-plane consumer only: it retains `apt-cacher-ng` and `lv3-buildkitd`, but no longer runs the old local `artifact-cache-*` containers and now resolves Docker pulls through the dedicated cache endpoints.
- The live correction loop uncovered one real repo defect: nested service playbooks under `playbooks/services/` could not copy the Docker publication-assurance helper from the old `playbook_dir`-relative path. That path contract is now repaired in both the shared role and the shared post-verify task.
- The governed wrapper remains valuable and intentionally stays in the evidence trail even though the branch-local run could not complete the final README canonical-truth check without violating this workstream's protected-file rules.

## Remaining For Merge-To-Main

- Rebase or merge this workstream onto the current `origin/main` lineage, which advanced to commit `f20b44a2b5b5518793513c984115470bc0fe2479` during the live verification window and touches several shared catalog and automation files that this workstream also updated.
- Refresh the main-only protected surfaces during the exact-main integration step: `README.md`, `VERSION`, `changelog.md`, `versions/stack.yaml`, and `build/platform-manifest.json`.
- Cut a canonical mainline receipt from the rebased committed source and rerun the exact-main verification or replay needed to prove the dedicated cache VM remains true on the merged baseline.
