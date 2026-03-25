# Intent Queue Runbook

## Purpose

Use this runbook to inspect and manually drain the ADR 0155 scheduler intent queue when a queued workflow is waiting on released scheduler resources.

## Queue State

- Scheduler queue state path: `LV3_SCHEDULER_INTENT_QUEUE_PATH` when set
- Default queue state path: git common dir `lv3-concurrency/scheduler-intent-queue.json`
- Queue entries remain separate from ADR 0162 deadlock queue state in `platform/intent_queue/store.py`

## Manual Inspection

- Show queue state:

```bash
python3 - <<'PY'
from pathlib import Path
from platform.intent_queue import SchedulerIntentQueueStore
store = SchedulerIntentQueueStore(repo_root=Path("."))
print(store.stats())
PY
```

- Inspect recent queue events:

```bash
rg 'intent\.(queued|dispatched|expired)' .local/state/ledger/ledger.events.jsonl
```

## Manual Dispatch

- Run one manual dispatcher pass from the repo checkout:

```bash
make intent-queue-dispatcher
```

- Target the pass to one released resource or workflow:

```bash
python3 scripts/intent_queue_dispatcher.py --repo-root . --resource-hint service:netbox --workflow-hint rotate-netbox-db-password
```

## Windmill Verification

- Confirm the seeded script:

```bash
python3 config/windmill/scripts/intent-queue-dispatcher.py --repo-root .
```

- After live apply, verify in Windmill that:
  - `f/lv3/intent_queue_dispatcher` exists and uses `python3`
  - `f/lv3/intent_queue_dispatcher_every_minute` is enabled

## Failure Modes

- If the queue grows but the dispatcher never runs, verify the Windmill worker checkout includes the new script and that the minute schedule is enabled.
- If items keep requeueing with `conflict_rejected` or `concurrency_limit`, inspect the active blocking intent and lane state before manually replaying again.
- If queued items expire, investigate the blocking resource and consider ADR 0162 deadlock detection before widening queue TTLs.
