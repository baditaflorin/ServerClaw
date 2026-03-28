# Workstream ws-0189-live-apply: ADR 0189 Live Apply From Latest `origin/main`

- ADR: [ADR 0189](../adr/0189-network-impairment-test-matrix-for-staging-and-previews.md)
- Title: live apply, validation, and evidence capture for the ADR 0189 network impairment matrix workflow
- Status: implemented
- Implemented In Repo Version: 0.177.20
- Live Applied In Platform Version: 0.130.31
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-27
- Branch: `codex/ws-0189-live-apply`
- Worktree: `.worktrees/ws-0189-live-apply`
- Owner: codex
- Depends On: `adr-0088-ephemeral-fixtures`, `adr-0167-graceful-degradation-mode-declarations`, `adr-0171-controlled-fault-injection`, `adr-0185-branch-scoped-ephemeral-preview-environments`
- Conflicts With: none
- Shared Surfaces: `config/network-impairment-matrix.yaml`, `platform/faults/network_impairment_matrix.py`, `scripts/network_impairment_matrix.py`, `config/windmill/scripts/network-impairment-matrix.py`, `config/workflow-catalog.json`, `config/command-catalog.json`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`, `docs/runbooks/network-impairment-matrix.md`, `receipts/live-applies/`

## Scope

- ship a repo-managed ADR 0189 network impairment matrix backed by the existing service degradation and fault catalogs
- expose a safe diagnostic workflow through Windmill so operators can render the current staging, preview, fixture, standby, and recovery plan from the released checkout
- validate the repo automation path, replay the live Windmill surface from the latest `origin/main`, and capture end-to-end evidence

## Non-Goals

- directly impairing production network paths as part of the live apply
- implementing full preview-environment creation under ADR 0185 in the same workstream
- changing protected integration files on this branch

## Expected Repo Surfaces

- `config/network-impairment-matrix.yaml`
- `platform/faults/network_impairment_matrix.py`
- `scripts/network_impairment_matrix.py`
- `config/windmill/scripts/network-impairment-matrix.py`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `docs/runbooks/network-impairment-matrix.md`
- `docs/adr/0189-network-impairment-test-matrix-for-staging-and-previews.md`
- `docs/workstreams/ws-0189-live-apply.md`

## Expected Live Surfaces

- `f/lv3/network-impairment-matrix` exists on the Windmill worker
- the live worker can render the staging slice from the released checkout
- `.local/network-impairment-matrix/latest.json` is written by the governed workflow run

## Verification

- `python3 -m py_compile scripts/network_impairment_matrix.py config/windmill/scripts/network-impairment-matrix.py platform/faults/network_impairment_matrix.py`
- `uv run --with pytest --with pyyaml python -m pytest tests/test_network_impairment_matrix.py tests/test_network_impairment_matrix_repo_surfaces.py tests/test_network_impairment_matrix_windmill.py -q`
- `uv run --with pyyaml python scripts/network_impairment_matrix.py --repo-path /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server --validate`
- `make syntax-check-windmill`
- `uv run --with pyyaml python scripts/workflow_catalog.py --validate`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `make network-impairment-matrix NETWORK_IMPAIRMENT_MATRIX_ARGS='target_class=staging'`
- `make live-apply-service service=windmill env=production EXTRA_ARGS='-e bypass_promotion=true'`

## Outcome

- The workstream started from `origin/main` commit `73121fc9e2ac3272e59706a01f090535e32cbed9` in repo release context `0.177.12`.
- The final `main` integration shipped in repo version `0.177.20`; the merge recorded the release metadata and canonical receipt mapping without forcing an extra platform-version bump because the live proof was already captured on `2026-03-27`.
- The ADR 0189 repo surface now ships the matrix catalog, report renderer, Windmill wrapper, validation hooks, and focused tests from the isolated `codex/ws-0189-live-apply` worktree.
- The initial governed live run exposed a shared Windmill worker regression where stale `/srv/proxmox_florin_server/pyproject.toml` and `lv3_platform_cli.egg-info` forced `uv` editable-build startup failures; the Windmill runtime role now prunes that stale packaging metadata during checkout refresh and the seeded matrix wrapper falls back to `uv` when the native worker environment lacks `PyYAML`.
- `GET /api/w/lv3/scripts/get/p/f%2Flv3%2Fnetwork-impairment-matrix` returned the live repo-managed script with hash `65063c8a80599a06`, and `POST /api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fnetwork-impairment-matrix` returned `status: planned`, `entry_count: 4`, `target_class: staging`, and `report_file: /srv/proxmox_florin_server/.local/network-impairment-matrix/latest.json`.
- The guest-local report at `/srv/proxmox_florin_server/.local/network-impairment-matrix/latest.json` exists on `docker-runtime-lv3` and records the same `planned` staging slice with four entries.
- The shared Windmill runtime repair was validated by replaying the older `fault-injection` script through the same API path in `dry_run` mode; it returned `status: planned` again after the worker-checkout cleanup.
- Focused validation passed with `python3 -m py_compile`, `11` focused pytest cases, `make syntax-check-windmill`, `uv run --with pyyaml python scripts/workflow_catalog.py --validate`, `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`, and `make pre-push-gate`; local `make validate` still stops on unrelated pre-existing `ansible-lint` warnings outside the ADR 0189 surface.
- The structured live evidence is recorded in `receipts/live-applies/2026-03-27-adr-0189-network-impairment-matrix-live-apply.json`.

## Mainline Integration

- The protected integration files are now complete on `main`: `VERSION` advanced to `0.177.20`, the release notes were cut, the canonical receipt mapping now includes `network_impairment_matrix`, and the README/generated truth surfaces were refreshed.
- No additional merge-to-main cleanup remains for ADR 0189.
