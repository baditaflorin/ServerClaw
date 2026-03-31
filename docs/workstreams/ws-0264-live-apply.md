# Workstream ws-0264-live-apply: Live Apply ADR 0264 From Latest `origin/main`

- ADR: [ADR 0264](../adr/0264-failure-domain-isolated-validation-lanes.md)
- Title: Partition repository validation into failure-domain-isolated lanes, then verify the build-server plus worker automation end to end
- Status: live_applied
- Implemented In Repo Version: 0.177.84
- Live Applied In Platform Version: 0.130.58
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/adr-0264-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/adr-0264-live-apply`
- Owner: codex
- Depends On: `ws-0264-receipt-driven-resilience-adrs`, `adr-0087-validation-gate`, `adr-0167-workstream-handoff-protocol`, `adr-0173-workstream-surface-ownership-manifest`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0264-failure-domain-isolated-validation-lanes.md`, `docs/workstreams/ws-0264-live-apply.md`, `docs/runbooks/validation-gate.md`, `.config-locations.yaml`, `docs/adr/.index.yaml`, `config/build-server.json`, `config/validation-gate.json`, `config/validation-lanes.yaml`, `config/workflow-catalog.json`, `config/windmill/scripts/post-merge-gate.py`, `config/windmill/scripts/gate-status.py`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`, `docs/diagrams/agent-coordination-map.excalidraw`, `scripts/gate_status.py`, `scripts/parallel_check.py`, `scripts/remote_exec.sh`, `scripts/run_gate.py`, `scripts/run_python_with_packages.sh`, `scripts/validate_repo.sh`, `scripts/validation_lanes.py`, `scripts/workstream_surface_ownership.py`, `tests/test_config_merge_repo_surfaces.py`, `tests/test_parallel_check.py`, `tests/test_post_merge_gate.py`, `tests/test_validate_repo_cache.py`, `tests/test_validation_gate.py`, `tests/test_validation_gate_windmill.py`, `tests/test_validation_lanes.py`, `tests/test_windmill_operator_admin_app.py`, `tests/test_workstream_surface_ownership.py`, `receipts/live-applies/2026-03-29-adr-0264-failure-domain-isolated-validation-lanes-mainline-live-apply.json`, `workstreams.yaml`

## Scope

- add the ADR 0264 lane catalog so every mutable surface class declares its required validation lanes
- keep fast global invariants blocking while unrelated heavy validations become non-blocking for focused changes
- propagate lane selection and reusable green-path evidence through the local runner, remote build-server validation, and worker-side post-merge entrypoint
- verify the latest-main replay on the managed Windmill runtime instead of stopping at branch-local tests

## Non-Goals

- merging neighboring ADR 0265 through ADR 0273 ownership into this workstream
- changing protected release files before the exact-main integration step
- weakening validation coverage for broad or integration-heavy changes

## Expected Repo Surfaces

- `config/validation-lanes.yaml`
- `config/validation-gate.json`
- `config/windmill/scripts/post-merge-gate.py`
- `config/windmill/scripts/gate-status.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `scripts/gate_status.py`
- `scripts/parallel_check.py`
- `scripts/remote_exec.sh`
- `scripts/run_gate.py`
- `scripts/run_python_with_packages.sh`
- `scripts/validate_repo.sh`
- `scripts/validation_lanes.py`
- `scripts/workstream_surface_ownership.py`
- `docs/adr/0264-failure-domain-isolated-validation-lanes.md`
- `docs/workstreams/ws-0264-live-apply.md`
- `docs/runbooks/validation-gate.md`
- `docs/adr/.index.yaml`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `tests/test_config_merge_repo_surfaces.py`
- `tests/test_parallel_check.py`
- `tests/test_post_merge_gate.py`
- `tests/test_validate_repo_cache.py`
- `tests/test_validation_gate.py`
- `tests/test_validation_gate_windmill.py`
- `tests/test_validation_lanes.py`
- `tests/test_windmill_operator_admin_app.py`
- `tests/test_workstream_surface_ownership.py`
- `receipts/live-applies/2026-03-29-adr-0264-failure-domain-isolated-validation-lanes-mainline-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- `make pre-push-gate` selects only the lanes owned by changed surfaces plus fast global invariants
- `make gate-status` records the same lane catalog and reusable lane evidence summaries on the integrated tree
- `make remote-validate` propagates the changed-surface lane context onto `docker-build-lv3`
- the worker-side `post-merge-gate.py` fallback validates only worker-safe stages when the checkout lacks `.git`

## Ownership Notes

- this workstream owns the ADR 0264 lane catalog, runner logic, Windmill fallback behavior, and the supporting runbook and tests
- protected release files remained deferred until the later mainline integration step
- the exact-main replay discovered additional Windmill runtime hardening that now ships with ADR 0264 because the worker path is part of the promised evidence surface

## Verification

- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_validation_lanes.py tests/test_validation_gate.py tests/test_validation_gate_windmill.py tests/test_validate_repo_cache.py tests/test_parallel_check.py tests/test_workstream_surface_ownership.py tests/test_config_merge_repo_surfaces.py tests/test_windmill_operator_admin_app.py tests/test_post_merge_gate.py`
- `./scripts/validate_repo.sh data-models workstream-surfaces agent-standards`
- `make pre-push-gate`
- `make gate-status`
- `make remote-validate`
- `python3 config/windmill/scripts/gate-status.py --repo-path /srv/proxmox_florin_server`
- `python3 config/windmill/scripts/post-merge-gate.py --repo-path /srv/proxmox_florin_server`

## Branch-Local Results

- the lane-aware implementation and focused regression slice passed locally before the exact-main replay, and the final integrated tree regression sweep returned `72 passed` across the ADR 0264 test slice
- the latest synchronized `origin/main` release cut advanced repository version `0.177.83` to `0.177.84`, and platform version `0.130.58` is the first integrated platform version that records ADR 0264 as verified from the current mainline
- the exact-main `playbooks/windmill.yml --limit docker-runtime-lv3` replay exposed a missing `pyyaml` dependency in the repo-managed schedule sync step, so the Windmill runtime now runs that script through `uv run --no-project --with pyyaml python3`
- the same replay showed the worker mirror could keep stale exact-worktree files, so the runtime role now tracks explicit checkout integrity files for the validation lane catalog and its Windmill task surfaces, then asserts the refreshed checksums match the controller state
- once the worker mirror held the latest ADR 0264 files, the worker-local `post-merge-gate.py` fallback exposed a gitless-checkout bug; the fallback is now split between git-required stages and worker-safe stages so the mirror can validate safely without pretending `.git` exists
- the full exact-main Windmill replay completed successfully with final recap `docker-runtime-lv3 : ok=251 changed=49 unreachable=0 failed=0 skipped=33 rescued=0 ignored=0`
- the worker mirror still needed one bounded manual repair during this live apply: the exact validation surfaces were refreshed into `/srv/proxmox_florin_server`, `/opt/windmill/worker-checkout.sha256` was removed, and the recovery step is now documented in the validation-gate runbook
- after the worker refresh and a worker-side canonical truth rewrite, `python3 config/windmill/scripts/gate-status.py --repo-path /srv/proxmox_florin_server` returned `status: ok`, and `python3 config/windmill/scripts/post-merge-gate.py --repo-path /srv/proxmox_florin_server` returned `status: ok` while running the worker-safe fallback validation plus `scripts/provider_boundary_catalog.py --validate`
- the canonical exact-main evidence is recorded in `receipts/live-applies/2026-03-29-adr-0264-failure-domain-isolated-validation-lanes-mainline-live-apply.json`

## Merge Criteria

- focused ADR, docs, or service changes no longer hard-block on unrelated validation lanes by default
- lane ownership is derived from committed repository metadata instead of ad hoc command-line conventions
- build-server, local, and worker fallback paths all record the same lane-aware evidence model

## Exact-Main Outcome

- release `0.177.84` now carries both the ADR 0264 implementation and the exact-main worker-path hardening onto `main`
- platform version `0.130.58` is the first integrated platform version that records the lane-aware validation gate plus the worker-safe post-merge fallback as verified together
- merge-to-main follow-through after this doc update is operational only: complete the final integrated-tree gate run, commit, fast-forward `main`, and push `origin/main`
