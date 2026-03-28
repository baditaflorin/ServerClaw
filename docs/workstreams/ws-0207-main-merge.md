# Workstream WS-0207 Main Merge

- ADR: [ADR 0207](../adr/0207-anti-corruption-layers-at-provider-boundaries.md)
- Title: Integrate the verified ADR 0207 live apply into `origin/main`
- Status: merged
- Branch: `codex/ws-0207-main-recut`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0207-main-recut`
- Owner: codex
- Depends On: `ws-0207-live-apply`

## Scope

- merge the finished ADR 0207 provider-boundary refactor onto the latest `origin/main`
- refresh the workstream registry, ADR metadata, receipts, and release-facing truth surfaces on the merged tree
- prove the integrated branch through local validation, the authoritative build-server `remote-validate` pass on the merged `0.177.38` tree, the final `0.177.41` `remote-validate` fallback pass, worker post-merge gate replay, and a governed live Hetzner DNS reconcile

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_validate_repo_cache.py tests/test_validate_alert_rules.py tests/test_windmill_operator_admin_app.py tests/test_config_merge_windmill.py tests/test_post_merge_gate.py tests/test_provider_boundary_catalog.py tests/test_hetzner_dns_record_role.py tests/test_hetzner_dns_records_role.py tests/test_plane_client.py tests/test_remote_exec.py tests/test_validation_gate.py tests/test_closure_loop_windmill.py tests/test_config_merge_repo_surfaces.py tests/test_correction_loops.py tests/test_incident_triage.py tests/test_live_apply_receipts.py tests/unit/test_closure_loop.py tests/test_validate_dependency_direction.py tests/test_dependency_direction_gate.py tests/test_health_composite.py tests/test_lv3_cli.py -q` passed with `178 passed in 25.22s` on the merged `0.177.41` tree before the final push
- `./scripts/validate_repo.sh generated-vars role-argument-specs json alert-rules data-models generated-docs generated-portals agent-standards` passed on the merged `0.177.41` release tree; it still emitted the existing non-blocking `.repo-structure.yaml` warning while exiting `0`
- `make remote-validate` proved both repo automation paths: the merged `0.177.38` tree completed the authoritative build-server manifest end to end, and the final merged `0.177.41` recut re-ran the same target successfully through the local fallback after build-server `rsync` hit `failed to set times` under `build/docs-portal/*`
- `python3 scripts/run_gate.py --workspace . --status-file .local/validation-gate/recheck.json --source local-fallback --print-json` passed all 14 manifest checks on the final `0.177.41` tree after the pre-push gate surfaced and this branch fixed one duplicate `coolify_runtime` YAML key plus the `post-merge-gate.py` fallback typing annotations
- the worktree-pinned Windmill replay succeeded with `docker-runtime-lv3 : ok=220 changed=39 failed=0` when run with `-e windmill_worker_checkout_repo_root_local_dir=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0207-main-recut`
- the updated guest-local `post-merge-gate.py` now returns `status: ok` for the worker-safe fallback command chain and captures the primary gate's registry image failures separately
- `VERSION`, `RELEASE.md`, `docs/release-notes/0.177.41.md`, `README.md`, `versions/stack.yaml`, and `workstreams.yaml` now record the merged ADR 0207 truth before the final push to `origin/main`
