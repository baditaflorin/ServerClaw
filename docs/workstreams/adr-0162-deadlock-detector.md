# Workstream ADR 0162: Distributed Deadlock Detection and Resolution

- ADR: [ADR 0162](../adr/0162-distributed-deadlock-detection-and-resolution.md)
- Title: Worker-shared lock registry, coordination map, intent queue, and 30-second Windmill deadlock detector with automatic loser requeue
- Status: live_applied
- Implemented In Repo Version: 0.150.0
- Implemented In Platform Version: 0.130.11
- Implemented On: 2026-03-26
- Branch: `codex/adr-0162-deadlock-detector`
- Worktree: `.worktrees/adr-0162-deadlock-detector`
- Owner: codex
- Depends On: `adr-0115-mutation-ledger`, `adr-0119-budgeted-scheduler`, `adr-0124-event-taxonomy`
- Conflicts With: none
- Shared Surfaces: `platform/locking/`, `platform/coordination/`, `platform/intent_queue/`, `config/windmill/scripts/`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`, `config/event-taxonomy.yaml`

## Scope

- add the ADR 0153-0162 document set to current `main` lineage and implement the runtime needed for ADR 0162
- create a worker-shared resource lock registry with TTL, hierarchy, and release-all support
- create a worker-shared coordination map with heartbeat TTL pruning
- create a worker-shared intent queue with retry and delay support
- create the deadlock detector plus livelock detection and automatic loser requeue
- seed a Windmill wrapper and a 30-second schedule through the existing Windmill runtime role
- register the new execution events and ledger event type
- document the operator/runtime path in a dedicated runbook

## Non-Goals

- implementing ADR 0154 execution lanes
- implementing a JetStream KV backend in this workstream
- operator-facing UI for concurrency state

## Expected Repo Surfaces

- `platform/locking/`
- `platform/coordination/`
- `platform/intent_queue/`
- `config/windmill/scripts/detect-deadlocks.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `config/event-taxonomy.yaml`
- `config/ledger-event-types.yaml`
- `docs/runbooks/deadlock-detection.md`
- `docs/adr/0153-distributed-resource-lock-registry.md`
- `docs/adr/0155-intent-queue-with-release-triggered-scheduling.md`
- `docs/adr/0161-real-time-agent-coordination-map.md`
- `docs/adr/0162-distributed-deadlock-detection-and-resolution.md`

## Expected Live Surfaces

- Windmill workspace `lv3` contains the script `f/lv3/detect_deadlocks`
- Windmill schedule `f/lv3/detect_deadlocks_every_30s` is present and enabled
- the worker checkout creates the shared state files on first detector run
- deadlock aborts write `execution.deadlock_aborted` into the configured ledger sink when present

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_deadlock_detector.py tests/test_deadlock_repo_surfaces.py tests/unit/test_event_taxonomy.py tests/unit/test_ledger_writer.py -q`
- `uv run --with pyyaml python scripts/validate_nats_topics.py --validate`
- `python3 -m py_compile config/windmill/scripts/detect-deadlocks.py`
- `ANSIBLE_CONFIG=ansible.cfg ANSIBLE_COLLECTIONS_PATH=collections uvx --from ansible-core ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --syntax-check`

## Merge Criteria

- the detector breaks a synthetic two-party cycle and requeues the lowest-priority participant
- the Windmill runtime seeds the detector script and enabled schedule
- event taxonomy and control-plane lanes cover the new execution subjects
- the runbook explains the state files, manual run path, and verification commands

## Notes For The Next Assistant

- the first repository implementation is intentionally file-backed so it works in local tests and on the mounted Windmill worker checkout without a separate JetStream client dependency
- if a later workstream introduces a JetStream KV backend, keep the current Python interfaces stable so the detector and wrapper do not need to change
- the 2026-03-26 completion path used a temporary jump-based inventory through `ops@100.64.0.1` because the controller could not reach `10.10.10.20` and `10.10.10.50` directly
- live recovery required realigning the `windmill_admin` PostgreSQL role password on `postgres` before Windmill could finish the ADR 0162 runtime verification path
- `config/windmill/scripts/detect-deadlocks.py` now resolves imports from the mounted checkout default `/srv/proxmox-host_server`, which is required for Windmill `run_wait_result` execution
