# Workstream ADR 0207: Anti-Corruption Layers At Provider Boundaries

- ADR: [ADR 0207](../adr/0207-anti-corruption-layers-at-provider-boundaries.md)
- Title: Translate critical provider payloads into canonical internal facts and enforce that contract in validation
- Status: implemented
- Branch: `codex/ws-0207-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0207-live-apply`
- Owner: codex
- Depends On: `adr-0206-ports-and-adapters-for-external-integrations`, `adr-0210-canonical-domain-models-over-vendor-schemas`, `adr-0213-architecture-fitness-functions-in-the-validation-gate`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/adr/0207-anti-corruption-layers-at-provider-boundaries.md`, `docs/workstreams/adr-0207-anti-corruption-layers-at-provider-boundaries.md`, `config/provider-boundary-catalog.yaml`, `scripts/provider_boundary_catalog.py`, `config/validation-gate.json`, `scripts/check_role_argument_specs.sh`, `scripts/controller_automation_toolkit.py`, `scripts/remote_exec.sh`, `scripts/validate_repo.sh`, `config/windmill/scripts/post-merge-gate.py`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/`, `collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/`, `docs/runbooks/remote-build-gateway.md`, `docs/runbooks/subdomain-governance.md`, `docs/runbooks/validate-repository-automation.md`, `docs/runbooks/validation-gate.md`, `tests/test_post_merge_gate.py`, `tests/test_remote_exec.py`, `tests/test_validate_repo_cache.py`, `tests/test_windmill_operator_admin_app.py`
- Ownership Manifest: `workstreams.yaml` `ownership_manifest`

## Scope

- add a repo-managed catalog of provider boundaries that must keep raw provider payloads edge-local
- wire the provider-boundary validation into `make validate`, the remote validation gate, and the Windmill post-merge gate
- refactor the Hetzner DNS roles so matching and drift logic uses canonical DNS facts instead of raw Hetzner response fields
- capture live-apply evidence that the merged-main validation path and a live DNS reconcile both passed

## Non-Goals

- rewriting every service-specific operator CLI around canonical models in one pass
- changing release files on the branch-local workstream path
- changing canonical `versions/stack.yaml` until the final merged-main integration step

## Expected Repo Surfaces

- `docs/adr/0207-anti-corruption-layers-at-provider-boundaries.md`
- `docs/workstreams/adr-0207-anti-corruption-layers-at-provider-boundaries.md`
- `docs/adr/.index.yaml`
- `workstreams.yaml`
- `config/provider-boundary-catalog.yaml`
- `config/ansible-role-idempotency.yml`
- `.config-locations.yaml`
- `scripts/controller_automation_toolkit.py`
- `scripts/provider_boundary_catalog.py`
- `config/windmill/scripts/post-merge-gate.py`
- `scripts/remote_exec.sh`
- `scripts/validate_repo.sh`
- `config/validation-gate.json`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/README.md`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/tasks/record.yml`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/README.md`
- `platform/ansible/plane.py`
- `docs/runbooks/remote-build-gateway.md`
- `docs/runbooks/subdomain-governance.md`
- `docs/runbooks/validate-repository-automation.md`
- `docs/runbooks/validation-gate.md`
- `tests/test_plane_client.py`
- `tests/test_post_merge_gate.py`
- `tests/test_remote_exec.py`
- `tests/test_provider_boundary_catalog.py`
- `tests/test_hetzner_dns_record_role.py`
- `tests/test_hetzner_dns_records_role.py`
- `tests/test_validate_repo_cache.py`
- `tests/test_windmill_operator_admin_app.py`

## Expected Live Surfaces

- live DNS reconciliation through the governed Hetzner DNS role path
- build-server `remote-validate` execution using the merged-main validation manifest, plus a final local-fallback replay on the recut tree
- Windmill post-merge validation from the mirrored worker checkout after the repo sync replay

## Ownership Notes

- the workstream owns the provider-boundary catalog, validator, Hetzner DNS role refactor, and the matching runbook updates
- the workstream also repairs the current-main validation drift in `config/ansible-role-idempotency.yml` so the full repo gate can run honestly while ADR 0207 tightens the merge gate
- the workstream also removes one existing ad hoc retry loop from `platform/ansible/plane.py` so the retry guard no longer blocks the full validation path on current `main`
- this workstream intentionally avoids `VERSION`, numbered `changelog.md` release sections, `README.md` integrated status, and `versions/stack.yaml` until final integration on `main`
- the first implementation assumes the highest-value provider boundary to harden immediately is the Hetzner DNS mutation path because it is shared by many live service converges and is already part of the governed live-apply workflow

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_validate_repo_cache.py tests/test_validate_alert_rules.py tests/test_windmill_operator_admin_app.py tests/test_config_merge_windmill.py tests/test_post_merge_gate.py tests/test_provider_boundary_catalog.py tests/test_hetzner_dns_record_role.py tests/test_hetzner_dns_records_role.py tests/test_plane_client.py tests/test_remote_exec.py tests/test_validation_gate.py tests/test_closure_loop_windmill.py tests/test_config_merge_repo_surfaces.py tests/test_correction_loops.py tests/test_incident_triage.py tests/test_live_apply_receipts.py tests/unit/test_closure_loop.py tests/test_validate_dependency_direction.py tests/test_dependency_direction_gate.py tests/test_health_composite.py tests/test_lv3_cli.py -q` passed with `178 passed in 25.22s` on the merged `0.177.41` tree before the final push
- `./scripts/validate_repo.sh generated-vars role-argument-specs json alert-rules data-models generated-docs generated-portals agent-standards` passed on the merged `0.177.41` release tree; it still emitted the existing non-blocking `.repo-structure.yaml` warning while exiting `0`
- `make remote-validate` passed twice across the final merge: first as the authoritative build-server manifest on the merged `0.177.38` tree, then again on the merged `0.177.41` recut after `scripts/remote_exec.sh` fell back locally when build-server `rsync` could not set mtimes under `build/docs-portal/*`
- the live Windmill converge now succeeds with `docker-runtime-lv3 : ok=220 changed=39 failed=0` and prunes stale immutable files from the worker mirror
- the guest-local worker proof now succeeds from the mirrored checkout via `python3 /srv/proxmox_florin_server/config/windmill/scripts/post-merge-gate.py --repo-path /srv/proxmox_florin_server`, where the worker-safe fallback returns `status: ok` after `./scripts/validate_repo.sh generated-vars role-argument-specs json alert-rules generated-docs generated-portals` and `uv run --with pyyaml python3 scripts/provider_boundary_catalog.py --validate`
- the governed Hetzner DNS reconcile for `ops.lv3.org` still finishes `ok=19 changed=0 skipped=2 failed=0`

## Merge Criteria

- the provider-boundary catalog fails the repo gate if the Hetzner DNS roles leak raw provider payload selectors past the translation step
- the Hetzner DNS roles only use canonical DNS facts after the provider boundary translation tasks
- the merged-main validation path and the worker post-merge validation path both exercise the new provider-boundary guard successfully
- the workstream records exactly which shared integration updates still belong to the final `main` step

## Mainline Notes

- the Windmill worker replay must pin `windmill_worker_checkout_repo_root_local_dir` to the active worktree during multi-worktree integration, otherwise `/srv/proxmox_florin_server` can mirror the shared top-level checkout instead of the branch being verified
- the authoritative full-manifest proof comes from the merged `0.177.38` build-server `make remote-validate` run; after the `0.177.41` recut, the same target hit build-server `rsync` mtime errors under `build/docs-portal/*`, fell back locally, and still exited `0` because `scripts/remote_exec.sh` now preserves a Python 3.10+ interpreter for the login-shell fallback while `scripts/validate_repo.sh` resolves its direct Python validators through that contract
- the first push attempt after the `0.177.41` recut exposed two additional local-fallback gate issues on the integration tree: one duplicate `coolify_runtime` YAML key in `config/ansible-role-idempotency.yml` and loose payload typing in `config/windmill/scripts/post-merge-gate.py`; both were fixed before the final local `scripts/run_gate.py --workspace . --status-file .local/validation-gate/recheck.json --source local-fallback --print-json` pass
- the worker-local fallback remains the live proof that ADR 0207 checks pass even while the registry-backed `check-runner` images remain unavailable on `docker-runtime-lv3`

## Notes For The Next Assistant

- if more provider-boundary rollouts follow, extend `config/provider-boundary-catalog.yaml` and the validator instead of cloning one-off grep checks
- treat raw provider payloads as debug-only artifacts; if a new receipt or generated doc needs provider detail, expose it through a canonical field plus an explicitly marked edge-local debug block
