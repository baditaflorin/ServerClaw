# Deadlock Detection

## Purpose

This runbook covers ADR 0162: the repository-managed deadlock detector that scans the shared lock registry, coordination map, and intent queue, then aborts and requeues the lowest-priority participant when it finds a cycle.

## Canonical Sources

- ADR: [docs/adr/0162-distributed-deadlock-detection-and-resolution.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0162-distributed-deadlock-detection-and-resolution.md)
- lock registry: [platform/locking/registry.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/platform/locking/registry.py)
- detector: [platform/locking/deadlock_detector.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/platform/locking/deadlock_detector.py)
- coordination map: [platform/coordination/map.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/platform/coordination/map.py)
- intent queue: [platform/intent_queue/store.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/platform/intent_queue/store.py)
- Windmill wrapper: [config/windmill/scripts/detect-deadlocks.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/windmill/scripts/detect-deadlocks.py)

## Runtime State

The first repository implementation uses worker-shared JSON state under the git common dir when available, otherwise under `.local/state/` in the repo checkout.

Relevant override environment variables:

- `LV3_LOCK_REGISTRY_PATH`
- `LV3_COORDINATION_MAP_PATH`
- `LV3_INTENT_QUEUE_PATH`
- `LV3_LEDGER_FILE` or `LV3_LEDGER_DSN`

## Manual Run

Run one detector pass locally:

```bash
python3 config/windmill/scripts/detect-deadlocks.py --repo-path "$PWD"
```

Run one pass against explicit state files:

```bash
python3 config/windmill/scripts/detect-deadlocks.py \
  --repo-path "$PWD" \
  --lock-registry-path .local/state/lv3-concurrency/lock-registry.json \
  --coordination-map-path .local/state/lv3-concurrency/coordination-map.json \
  --intent-queue-path .local/state/lv3-concurrency/intent-queue.json \
  --ledger-file-path .local/state/lv3-concurrency/deadlock-ledger.jsonl
```

## Windmill Path

The Windmill runtime seeds:

- script: `f/lv3/detect_deadlocks`
- schedule: `f/lv3/detect_deadlocks_every_30s`

The schedule is intentionally enabled in repo-managed defaults because the detector is safe to run when the state files are empty; it returns a zero-findings payload.

## Verification

```bash
uv run --with pytest --with pyyaml python -m pytest \
  tests/test_deadlock_detector.py \
  tests/test_deadlock_repo_surfaces.py -q
```

```bash
ANSIBLE_CONFIG=ansible.cfg ANSIBLE_COLLECTIONS_PATH=collections \
  uvx --from ansible-core ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --syntax-check
```

## Operational Notes

- The detector prefers the highest numeric priority as the victim. Lower-urgency work should therefore use higher numeric priority values.
- Livelock is advisory only in this first implementation. The detector reports it but does not auto-abort the intent.
- Deadlock aborts are recorded as `execution.deadlock_aborted` ledger events when a ledger sink is configured.
