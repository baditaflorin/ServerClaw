# Workstream WS-0207 Main Merge

- ADR: [ADR 0207](../adr/0207-anti-corruption-layers-at-provider-boundaries.md)
- Title: Integrate the verified ADR 0207 live apply into `origin/main`
- Status: in-progress
- Branch: `codex/ws-0207-main-recut`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0207-main-recut`
- Owner: codex
- Depends On: `ws-0207-live-apply`

## Scope

- merge the finished ADR 0207 provider-boundary refactor onto the latest `origin/main`
- refresh the workstream registry, ADR metadata, receipts, and release-facing truth surfaces on the merged tree
- prove the integrated branch through local validation, build-server `remote-validate`, worker post-merge gate replay, and a governed live Hetzner DNS reconcile

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_validate_repo_cache.py tests/test_validate_alert_rules.py tests/test_windmill_operator_admin_app.py tests/test_config_merge_windmill.py tests/test_post_merge_gate.py tests/test_provider_boundary_catalog.py tests/test_hetzner_dns_record_role.py tests/test_hetzner_dns_records_role.py tests/test_plane_client.py tests/test_remote_exec.py tests/test_validation_gate.py -q` passed with `88 passed in 9.10s`
- the worktree-pinned Windmill replay succeeded with `docker-runtime-lv3 : ok=220 changed=39 failed=0` when run with `-e windmill_worker_checkout_repo_root_local_dir=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0207-main-recut`
- the updated guest-local `post-merge-gate.py` now returns `status: ok` for the worker-safe fallback command chain and captures the primary gate's registry image failures separately
- the remaining final integration steps are to rerun the branch-local repository gate, rerun `make remote-validate` from this branch head, fast-forward onto the latest `origin/main`, and push `origin/main`
