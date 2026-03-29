# Workstream ADR 0295: Artifact Cache Architecture Bundle

- ADR: [ADR 0295](../adr/0295-shared-artifact-cache-plane-for-container-and-package-dependencies.md)
- Title: Shared artifact-cache direction for reused container images now and
  npm or PyPI-style package caches later, with a phased path from
  `docker-build-lv3` to a dedicated cache VM
- Status: merged
- Branch: `codex/ws-0274-artifact-cache-plane`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0274-artifact-cache-plane`
- Owner: codex
- Depends On: `adr-0068-container-image-policy`,
  `adr-0082-remote-build-gateway`, `adr-0083-docker-check-runner`,
  `adr-0089-build-cache`,
  `adr-0274-governed-base-image-mirrors-and-warm-caches-for-repo-deployments`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0295-0296`, `docs/adr/.index.yaml`,
  `docs/workstreams/adr-0295-artifact-cache-architecture-bundle.md`,
  `workstreams.yaml`, `playbooks/services/build-artifact-cache.yml`,
  `collections/ansible_collections/lv3/platform/playbooks/services/build-artifact-cache.yml`,
  `collections/ansible_collections/lv3/platform/roles/artifact_cache_runtime/*`,
  `collections/ansible_collections/lv3/platform/roles/build_server/*`,
  `collections/ansible_collections/lv3/platform/roles/docker_runtime/*`,
  `docs/runbooks/artifact-cache-runtime.md`,
  `docs/runbooks/configure-build-artifact-cache.md`,
  `scripts/artifact_cache_seed.py`,
  `tests/test_artifact_cache_seed.py`,
  `tests/test_artifact_cache_runtime_role.py`

## Scope

- add ADR 0295 and ADR 0296 so the cache problem is captured as platform
  architecture, not just a one-off builder tweak
- land the first repo-managed container-image cache runtime on the build-host
  automation path
- seed cache warming from the repo's existing image manifests so expected pulls
  are explicit and repeatable
- keep the long-term path open for a dedicated `artifact-cache-lv3` VM without
  rewriting protected release truth on this branch

## Non-Goals

- changing `README.md`, `VERSION`, `changelog.md`, or `versions/stack.yaml`
  before an integration step
- claiming a live dedicated cache VM before merged truth and a real apply
- replacing ADR 0068 image governance with cache-local image truth

## Expected Repo Surfaces

- `docs/adr/0295-shared-artifact-cache-plane-for-container-and-package-dependencies.md`
- `docs/adr/0296-dedicated-artifact-cache-vm-with-phased-consumer-adoption.md`
- `docs/workstreams/adr-0295-artifact-cache-architecture-bundle.md`
- `docs/adr/.index.yaml`
- `workstreams.yaml`
- `playbooks/services/build-artifact-cache.yml`
- `collections/ansible_collections/lv3/platform/playbooks/services/build-artifact-cache.yml`
- `collections/ansible_collections/lv3/platform/roles/artifact_cache_runtime/`
- `collections/ansible_collections/lv3/platform/roles/build_server/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/build_server/meta/argument_specs.yml`
- `collections/ansible_collections/lv3/platform/roles/build_server/templates/buildkitd.toml.j2`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/meta/argument_specs.yml`
- `docs/runbooks/artifact-cache-runtime.md`
- `docs/runbooks/configure-build-artifact-cache.md`
- `scripts/artifact_cache_seed.py`
- `tests/test_artifact_cache_seed.py`
- `tests/test_artifact_cache_runtime_role.py`

## Expected Live Surfaces

- none yet; the initial cache landing is merged on `main` but still awaits a
  separate live-apply step

## Ownership Notes

- this workstream owns the architecture bundle and the first non-protected
  implementation surfaces
- the merge to `main` bumps repo release truth but leaves live platform truth
  untouched on purpose
- the dedicated VM remains a planned phase, not merged truth, until an
  integration or live-apply workstream claims it explicitly

## Verification

- run `uv run --with pyyaml python scripts/generate_adr_index.py --write`
- run `pytest tests/test_artifact_cache_seed.py tests/test_artifact_cache_runtime_role.py tests/test_docker_runtime_role.py`
- run `./scripts/validate_repo.sh agent-standards`

## Merge Criteria

- the ADRs must clearly separate cache-plane policy from dedicated-VM topology
- the implementation must improve the current build-host path without rewriting
  protected release truth
- another assistant must be able to continue from this worktree without hidden
  context

## Notes For The Next Assistant

- if phase 1 proves stable, the next implementation step is to add a real
  `artifact-cache-lv3` guest in inventory and then move the mirror endpoints off
  `docker-build-lv3`
- runtime-host adoption should happen after the dedicated VM exists so cache
  endpoints stop moving underneath consumers
