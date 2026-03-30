# Workstream WS-0296: Dedicated Artifact Cache VM Live Apply

- ADR: [ADR 0296](../adr/0296-dedicated-artifact-cache-vm-with-phased-consumer-adoption.md)
- Title: Provision `artifact-cache-lv3`, move the build host onto the dedicated cache plane, and record the exact live-apply proof from latest `origin/main`
- Status: live_applied
- Included In Repo Version: 0.177.103
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0296-dedicated-artifact-cache-vm-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0296-dedicated-artifact-cache-vm-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.69
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

- The exact-main focused regression slice in `receipts/live-applies/evidence/2026-03-30-ws-0296-mainline-targeted-checks-r2-0.177.103.txt` passed with `19 passed in 0.22s`, and `receipts/live-applies/evidence/2026-03-30-ws-0296-mainline-syntax-check-r2-0.177.103.txt` confirmed `make syntax-check-artifact-cache-vm` still succeeds from the exact-main release tree.
- The exact-main repository automation and validation paths also passed after receipt promotion: `uv run --with pyyaml python3 scripts/ansible_scope_runner.py validate --inventory inventory/hosts.yml`, the scoped `playbooks/services/build-artifact-cache.yml --syntax-check` replay, `uv run --with pyyaml --with jsonschema python3 scripts/validate_repository_data_models.py --validate`, `uv run --with pyyaml python3 scripts/canonical_truth.py --check`, `uv run --with pyyaml --with jsonschema python3 scripts/platform_manifest.py --check`, `./scripts/validate_repo.sh agent-standards`, and `git diff --check`.
- The remote pre-push gate also exposed stale generated docs after the canonical receipt promotion. Regenerating `docs/site-generated/architecture/dependency-graph.md` with `uv run --with jsonschema python3 scripts/generate_dependency_diagram.py --write` and refreshing `docs/diagrams/` with `uv run --with pyyaml python3 scripts/generate_diagrams.py --write` cleared the follow-up `./scripts/validate_repo.sh generated-docs` check.
- `make configure-artifact-cache-vm env=production` replayed successfully from repo version `0.177.103`, finishing with final recap `artifact-cache-lv3 : ok=118 changed=8 unreachable=0 failed=0 skipped=7 rescued=0 ignored=0` and `proxmox_florin : ok=14 changed=4 unreachable=0 failed=0 skipped=3 rescued=0 ignored=0`.
- The governed wrapper path `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=build-artifact-cache env=production EXTRA_ARGS='-e bypass_promotion=true'` then completed successfully from the exact-main release tree, including the canonical-truth gate that the earlier branch-local audit intentionally left stale before the protected integration step; the final recap was `docker-build-lv3 : ok=127 changed=11 unreachable=0 failed=0 skipped=18 rescued=0 ignored=0`.
- The exact-main end-to-end verification in `receipts/live-applies/evidence/2026-03-30-ws-0296-mainline-end-to-end-r1-0.177.103.txt` confirmed VM `180` serves all four cache ports locally with the repo-derived `51`-image warm set, `docker-build-lv3` now points its Docker mirrors and insecure registries at `10.10.10.80:5001-5004`, `docker buildx inspect lv3-cache --bootstrap` succeeds, and the old local `artifact-cache-*` containers are absent from the build guest.
- The earlier branch-local receipt remains in the branch as pre-integration audit history, but the canonical mainline receipt now records the exact-main live apply that matches the protected release and canonical-truth surfaces.
- `./scripts/validate_repo.sh workstream-surfaces` now fails by design on this branch because the validator rejects branch-to-terminal-workstream mappings once `ws-0296-live-apply` is marked `live_applied`; the earlier non-terminal pass remains in the branch-local evidence, and the promoted truth is now intended for `main` rather than continued branch mutation.

## Results

- VM `180` now exists as `artifact-cache-lv3` on `10.10.10.80/24` with the pinned MAC address `BC:24:11:18:AC:80`, `4` vCPUs, `8192` MiB RAM, `160` GiB disk, and the declared internal-only firewall policy.
- The dedicated cache runtime is live on `artifact-cache-lv3`, with `artifact-cache-docker-hub`, `artifact-cache-ghcr`, `artifact-cache-plane`, and `artifact-cache-n8n` all serving TCP `5001-5004` and the repo-derived `51`-image warm set now materialized on the dedicated guest instead of the build host.
- `docker-build-lv3` is now a cache-plane consumer only: it retains `apt-cacher-ng` and `lv3-buildkitd`, no longer runs the old local `artifact-cache-*` containers, and now resolves Docker pulls through the dedicated cache endpoints.
- The live correction loop uncovered one real repo defect: nested service playbooks under `playbooks/services/` could not copy the Docker publication-assurance helper from the old `playbook_dir`-relative path. That path contract is now repaired in both the shared role and the shared post-verify task.
- The governed wrapper now succeeds end to end from the exact-main release tree, while the earlier branch-local receipt remains available as the pre-integration audit trail that captured the deliberate README gate stop before the protected merge step.

## Remaining For Merge-To-Main

- None for ADR 0296 itself. The protected release and canonical-truth surfaces were refreshed during the exact-main integration step, and the canonical mainline receipt now supersedes the branch-local proof while preserving it as audit history.
- Broader runtime-host adoption beyond `docker-build-lv3` remains later phased work under the ADR, not a blocker for this live apply.
