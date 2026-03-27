# Workstream ADR 0153: Distributed Resource Lock Registry

- ADR: [ADR 0153](../adr/0153-distributed-resource-lock-registry.md)
- Title: Worker-shared typed resource locks with TTL, hierarchy, deadlock-detector integration, and controller-local inspection tooling
- Status: merged
- Implemented In Repo Version: 0.150.0
- Implemented In Platform Version: 0.130.12
- Implemented On: 2026-03-26
- Branch: `codex/adr-0153-distributed-resource-lock-registry`
- Worktree: `.worktrees/adr-0153`
- Owner: codex
- Depends On: `adr-0112-goal-compiler`, `adr-0115-mutation-ledger`, `adr-0119-budgeted-workflow-scheduler`, `adr-0127-intent-conflict-resolution`
- Conflicts With: `adr-0154-vm-scoped-execution-lanes`, `adr-0155-intent-queue-with-release-triggered-scheduling`
- Shared Surfaces: `platform/locking/`, `platform/scheduler/`, `platform/goal_compiler/`, `scripts/resource_lock_tool.py`, `Makefile`, `docs/runbooks/resource-lock-registry.md`

## Scope

- add the first repository implementation of ADR 0153 as a worker-shared lock registry with TTL pruning and hierarchy-aware conflict checks
- expose the registry through a controller-local inspection and mutation tool for operators and tests
- keep the lock contract stable for follow-on workstreams such as execution lanes, intent queue wake-ups, and deadlock detection
- restore the missing runbook and workstream metadata on later mainline revisions without regressing newer scheduler architecture

## Non-Goals

- claiming the JetStream KV backend is already the default runtime for the first repository implementation
- introducing lock-dashboard UI in this workstream
- rewinding the newer mainline scheduler architecture to the older ADR 0153 branch shape

## Expected Repo Surfaces

- `platform/locking/`
- `scripts/resource_lock_tool.py`
- `Makefile`
- `docs/runbooks/resource-lock-registry.md`
- `docs/adr/0153-distributed-resource-lock-registry.md`
- `docs/workstreams/adr-0153-distributed-resource-lock-registry.md`
- `tests/test_resource_lock_registry.py`
- `tests/test_resource_lock_tool.py`

## Expected Live Surfaces

- the worker checkout creates `lv3-concurrency/lock-registry.json` under the git common dir on first lock activity
- the deadlock detector and any scheduler path using `platform.locking` read the same shared state file within that checkout
- a controller-local smoke test can inspect and mutate an explicitly selected registry state file through `scripts/resource_lock_tool.py`

## Verification

- `python3 -m py_compile platform/locking/*.py scripts/resource_lock_tool.py`
- `uv run --with pytest python -m pytest -q tests/test_deadlock_detector.py tests/test_resource_lock_registry.py tests/test_resource_lock_tool.py`
- `make ensure-resource-lock-registry`
- `make resource-locks`

## Merge Criteria

- the lock registry enforces TTL expiry and hierarchy-aware conflicts
- operators can ensure, list, acquire, release, and heartbeat locks through a documented repo-local tool
- README generated status output includes the ADR 0153 workstream again on current `main`

## Outcome

- repository implementation first merged in repo release `0.150.0`
- current `main` now carries the missing ADR 0153 runbook, workstream record, and current-main-compatible lock tool without reintroducing the earlier divergent scheduler branch
- focused lock-registry and lock-tool tests cover duplicate refresh, heartbeat, release-all, CLI round-trip, and conflict handling
- release `0.161.0` completes the first current-mainline live replay for ADR 0153 on `2026-03-26` and advances platform version to `0.130.12`

## Live Apply Notes

- The first 2026-03-25 retry reached `proxmox_florin`, `postgres-lv3`, and `docker-runtime-lv3` but failed when the local OpenBao API on `docker-runtime-lv3` answered `503` with `sealed: true`.
- The recovery work identified a repo-owned timer bug: the OpenBao and Vaultwarden certificate-renew helpers reissued 24-hour certificates every 15 minutes, repeatedly restarting OpenBao and resealing it. The managed renewal threshold is now 6 hours instead of 24 hours.
- Recovery also required one manual Docker daemon restart on `docker-runtime-lv3` to restore the missing `nat` `DOCKER` chain and one manual OpenBao unseal using the existing controller-local recovery material after an interrupted replay left the runtime half-unsealed.
- Because this integration ran from a separate worktree, the worktree-local Windmill database password had diverged from the canonical controller-local secret already mirrored in OpenBao. Syncing the worktree secret back to the canonical root checkout was required before the successful current-mainline replay.
- Vaultwarden then exposed two current-mainline gaps during the same live replay: the admin-token hash generation path needed a TTY-aware `vaultwarden hash` invocation, and the controller-path verification could not rely on local DNS or default source-address selection on this workstation. The role now generates hashes through `script -qec`, persists non-empty hashes safely, and falls back to a Tailscale-bound controller probe when `vault.lv3.org` does not resolve locally.
- The successful current-mainline replay completed on `2026-03-26` through the production OpenBao, Windmill, and Vaultwarden converges. Direct verification confirmed Vaultwarden returned `200` on the published controller path, `CE v1.662.0`, healthy Windmill workers, an unsealed OpenBao API on `http://127.0.0.1:8201/v1/sys/health`, and a runtime `DATABASE_URL` matching the canonical controller-local secret.
