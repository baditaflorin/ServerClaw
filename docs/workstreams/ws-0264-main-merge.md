# Workstream ws-0264-main-merge

- ADR: [ADR 0264](../adr/0264-failure-domain-isolated-validation-lanes.md)
- Title: Integrate ADR 0264 exact-main replay onto `origin/main`
- Status: `merged`
- Included In Repo Version: 0.177.84
- Platform Version Observed During Integration: 0.130.58
- Release Date: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/adr-0264-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/adr-0264-main-integration`
- Owner: codex
- Depends On: `ws-0264-live-apply`

## Purpose

Carry the verified ADR 0264 lane-aware validation implementation onto the
latest available `origin/main`, refresh the protected release and canonical
truth surfaces for repository version `0.177.84`, and record the exact-main
Windmill replay that turns the branch-local lane partitioning into canonical
mainline evidence.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0264-main-merge.md`
- `docs/workstreams/ws-0264-live-apply.md`
- `docs/adr/0264-failure-domain-isolated-validation-lanes.md`
- `docs/runbooks/validation-gate.md`
- `.config-locations.yaml`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.84.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `config/validation-gate.json`
- `config/validation-lanes.yaml`
- `config/workflow-catalog.json`
- `config/windmill/scripts/post-merge-gate.py`
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
- `tests/test_config_merge_repo_surfaces.py`
- `tests/test_parallel_check.py`
- `tests/test_post_merge_gate.py`
- `tests/test_validate_repo_cache.py`
- `tests/test_validation_gate.py`
- `tests/test_validation_lanes.py`
- `tests/test_windmill_operator_admin_app.py`
- `tests/test_workstream_surface_ownership.py`
- `receipts/live-applies/2026-03-29-adr-0264-failure-domain-isolated-validation-lanes-mainline-live-apply.json`

## Verification

- `git fetch origin --prune` confirmed the newest published `origin/main` baseline had advanced to commit `2efaafb20c4f7d412fdbe821216493fa68d6bc53`, so the ADR 0264 stack was rebased onto that head before the final exact-main verification continued
- the rebased exact-main source commit `5ce5deae525879610a61c9065a63e951a21bc968` preserved the Windmill schedule-sync dependency fix, worker-checkout integrity sentinels, and gitless worker-fallback split on top of the latest available `origin/main`
- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_validation_lanes.py tests/test_validation_gate.py tests/test_validation_gate_windmill.py tests/test_validate_repo_cache.py tests/test_parallel_check.py tests/test_workstream_surface_ownership.py tests/test_config_merge_repo_surfaces.py tests/test_windmill_operator_admin_app.py tests/test_post_merge_gate.py` returned `72 passed in 4.78s`, and the focused post-patch worker-fallback slice `uv run --with pytest --with pyyaml python -m pytest -q tests/test_post_merge_gate.py tests/test_windmill_operator_admin_app.py tests/test_config_merge_repo_surfaces.py` returned `24 passed in 1.85s`
- `make pre-push-gate` passed on the rebased exact-main tree with the selected lanes `documentation-and-adr`, `repository-structure-and-schema`, `generated-artifact-and-canonical-truth`, `service-syntax-and-unit`, `remote-builder`, and `live-apply-and-promotion`; all blocking checks passed on `docker-build-lv3`
- `make remote-validate` passed on the rebased exact-main tree with the focused lane set `repository-structure-and-schema`, `generated-artifact-and-canonical-truth`, and `service-syntax-and-unit`
- the exact-main `playbooks/windmill.yml --limit docker-runtime-lv3` replay completed successfully with final recap `docker-runtime-lv3 : ok=251 changed=49 unreachable=0 failed=0 skipped=33 rescued=0 ignored=0`
- when the worker mirror still held stale exact-worktree files after replay, a bounded refresh of the rebased ADR 0264 validation surfaces into `/srv/proxmox_florin_server` plus removal of `/opt/windmill/worker-checkout.sha256` restored alignment and is now documented in the validation-gate runbook
- after removing macOS `._*` artifacts from the manual tar transfer and restoring `ops:ops` ownership on the worker checkout, `/usr/local/bin/uv run --with pyyaml python3 scripts/canonical_truth.py --write` refreshed worker canonical truth, `python3 config/windmill/scripts/gate-status.py --repo-path /srv/proxmox_florin_server` returned `status: ok`, and the final `python3 config/windmill/scripts/post-merge-gate.py --repo-path /srv/proxmox_florin_server` returned `status: ok` with the worker-safe fallback command `./scripts/validate_repo.sh generated-vars role-argument-specs json alert-rules generated-docs generated-portals && uv run --with pyyaml python3 scripts/provider_boundary_catalog.py --validate`
- the first rebased `make post-merge-gate` replay passed at `2026-03-29T17:55:49Z`; after the final worker-fallback hardening, a second controller-local replay timed out only `yaml-lint` at `120s` while every other check still passed, so the wrapper patch was treated as a worker-path-only follow-up and closed by the focused pytest slice plus the real worker rerun

## Outcome

- release `0.177.84` now carries the ADR 0264 failure-domain-isolated validation lanes plus the exact-main Windmill worker hardening on `main`
- platform version `0.130.58` is the first integrated platform version targeted by the canonical `validation_gate` receipt for the synchronized latest-main replay
- `receipts/live-applies/2026-03-29-adr-0264-failure-domain-isolated-validation-lanes-mainline-live-apply.json` is the canonical exact-main proof, while `docs/workstreams/ws-0264-live-apply.md` preserves the branch-local and worker-recovery narrative
