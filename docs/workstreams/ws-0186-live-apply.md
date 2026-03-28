# Workstream ws-0186-live-apply: Live Apply ADR 0186 From Latest `origin/main`

- ADR: [ADR 0186](../adr/0186-prewarmed-fixture-pools-and-lease-based-ephemeral-capacity.md)
- Title: Live apply the lease-based warm-pool reconciler and verify prewarmed fixture handoff from an isolated worktree
- Status: live_applied
- Implemented In Repo Version: 0.177.21
- Live Applied In Platform Version: 0.130.32
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0186-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0186-live-apply`
- Owner: codex
- Depends On: `adr-0088-ephemeral-fixtures`, `adr-0105-capacity-model`, `adr-0106-ephemeral-lifecycle`, `adr-0183-auxiliary-cloud-failure-domain-for-witness-recovery-and-burst-capacity`
- Conflicts With: none
- Shared Surfaces: `scripts/fixture_manager.py`, `config/ephemeral-capacity-pools.json`, `config/capacity-model.json`, `config/windmill/scripts/ephemeral-pool-reconciler.py`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`, `docs/runbooks/ephemeral-fixtures.md`, `tests/test_fixture_manager.py`, `tests/test_ephemeral_lifecycle_repo_surfaces.py`, `workstreams.yaml`

## Scope

- add a canonical pool catalog with warm counts, refill targets, lease ceilings, address allocation, and explicit auxiliary-domain spillover targets
- teach the fixture manager to prewarm stopped members, hand off warm fixtures as leases, and keep lease metadata visible without silently borrowing standby capacity
- seed a Windmill pool reconciler so the live platform can refill warm pools asynchronously after lease handoff
- verify the branch-local repo automation and then perform a full latest-main live replay from this separate worktree

## Verification

- `python3 -m py_compile scripts/fixture_manager.py config/windmill/scripts/ephemeral-pool-reconciler.py scripts/validate_repository_data_models.py scripts/lv3_cli.py`
- `uv run --with pytest python -m pytest -q tests/test_fixture_manager.py tests/test_ephemeral_lifecycle_repo_surfaces.py tests/test_validate_ephemeral_vmid.py tests/test_capacity_report.py`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `uv run --with pytest python -m pytest -q tests/test_fixture_manager.py tests/test_ephemeral_windmill_wrappers.py tests/test_ephemeral_lifecycle_repo_surfaces.py tests/test_validate_ephemeral_vmid.py tests/test_capacity_report.py`
- `make syntax-check-windmill`
- `make workflow-info WORKFLOW=ephemeral-pool-reconcile`
- `./scripts/validate_repo.sh agent-standards`
- `uv run --with pyyaml --with jsonschema python scripts/live_apply_receipts.py --validate`

## Live Evidence

- The isolated worktree was created from `origin/main` commit `73121fc9e2ac3272e59706a01f090535e32cbed9` on branch `codex/ws-0186-live-apply`.
- The live Windmill worker checkout and Windmill API both matched the branch-local `config/windmill/scripts/ephemeral-pool-reconciler.py` wrapper after replay, including file-path loading of `fixture_manager.py` and the worker-local bootstrap-key override.
- Controller-side live reconcile created `ops-base-20260327T230619Z` on VM `911`, verified guest access with `id ops >/dev/null`, and stopped it as a `prewarmed` pool member.
- A live lease handoff reused the same receipt and VM with `allocation_mode: "warm-handoff"`, `pool_state: "leased"`, `owner: "codex"`, and `purpose: "adr-0186-live-smoke"`, then passed the same guest verification over the Tailscale-backed Proxmox jump host.
- The leased warm member was destroyed cleanly, a refill provisioned fresh VM `912`, and the pool returned to `ready` with `warm_count: 1` through `python3 scripts/fixture_manager.py pool-status --json`.
- The committed branch-local live-apply receipt is `receipts/live-applies/2026-03-28-adr-0186-prewarmed-fixture-pools-live-apply.json`.

## Live Observations

- The live `run_wait_result` Windmill path returned `script not found` for script-path execution during this replay even for existing scripts, so the proof relied on direct API content verification plus controller-side execution against the same repo-managed code.
- The local `docker run ... tofu apply` path could create and boot the warm member but lingered inside the Proxmox provider create wait even after guest SSH was healthy. Both verified prewarm receipts were therefore completed with a bounded repo-function recovery step that re-used the already-created VM, verified the guest, stopped it, retagged it, and saved the governed receipt.
- `docker-host` and `postgres-host` remain declared in the governed pool catalog and visible in `fixture-pool-status`; the live replay focused on `ops-base` because it exercises the full shared warm-pool lease path without consuming additional local burst capacity.

## Outcome

- ADR 0186 is implemented and branch-locally live-applied from the dedicated worktree.
- The governed warm-pool catalog, warm-handoff lease path, asynchronous Windmill refill automation, and live evidence are now merged on `main`.

## Mainline Integration

- merged to `main` in repository version `0.177.21`
- no new platform version bump was required during the mainline merge because the verified ADR 0186 live state was already present on platform version `0.130.32`
- release `0.177.21` also carried the already-pending ADR 0190 repository release note from the newer `origin/main` baseline that this merge was integrated against
