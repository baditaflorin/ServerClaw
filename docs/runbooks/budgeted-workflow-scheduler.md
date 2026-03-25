# Budgeted Workflow Scheduler

## Purpose

ADR 0119 inserts a repository-managed scheduler between `lv3 run` and Windmill. The scheduler loads per-workflow budgets, enforces concurrency and rollback-depth guards, and runs a watchdog over active mutation jobs.

ADR 0172 extends that watchdog so it can also:

- discover running mutation jobs directly from Windmill
- abort stale jobs after `90` seconds without observed activity
- emit a repeated-action finding after three identical self-healing actions in ten minutes
- write `.local/scheduler/watchdog-heartbeat.json` on every tick

## Canonical Sources

- scheduler package: [platform/scheduler](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/scheduler)
- workflow defaults: [config/workflow-defaults.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-defaults.yaml)
- workflow catalog budgets: [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json)
- watchdog entry point: [windmill/scheduler/watchdog-loop.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/windmill/scheduler/watchdog-loop.py)
- Windmill seed defaults: [collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml)

## Operator Paths

Interactive workflow execution now routes through the scheduler:

```bash
lv3 run converge-netbox
```

Run one watchdog pass locally:

```bash
make scheduler-watchdog-loop
```

Expected live Windmill script and schedule:

```text
f/lv3/scheduler_watchdog_loop
f/lv3/scheduler_watchdog_loop_every_10s
```

Inspect one workflow budget:

```bash
python3 scripts/workflow_catalog.py --workflow converge-netbox
```

## Budget Model

- `config/workflow-defaults.yaml` defines the baseline budget applied when a workflow does not override a field.
- `config/workflow-catalog.json` can override any budget field per workflow and declares `execution_class`.
- Only `execution_class: mutation` workflows are subject to scheduler budget enforcement.
- Host-touch limits are advisory in this first implementation unless the workflow supplies an explicit host list in its input arguments.

## State And Locks

- Active jobs are tracked in `.local/scheduler/active-jobs.json`.
- The watchdog also queries Windmill for running jobs so the scheduled loop can operate without sharing the controller-local state file.
- Concurrency uses Postgres advisory transaction locks when `LV3_LEDGER_DSN` is present.
- Without a ledger DSN, the scheduler falls back to repo-local file locks under `.local/scheduler/locks/`.
- The watchdog heartbeat is written to `.local/scheduler/watchdog-heartbeat.json`.
- Recent self-healing actions are tracked in `.local/scheduler/watchdog-actions.json`.

## Troubleshooting

`lv3 run ...` returns `concurrency_limit`:
- another instance of the same mutation workflow is already active
- confirm with `.local/scheduler/active-jobs.json`

`lv3 run ...` returns `rollback_depth_exceeded`:
- the supplied `parent_actor_intent_id` chain already exceeds the budgeted rollback depth
- inspect `ledger.events` for the prior scheduler lifecycle records

`make scheduler-watchdog-loop` returns `blocked`:
- verify the repo checkout path exists on the worker
- export `LV3_WINDMILL_BASE_URL` and `LV3_WINDMILL_TOKEN`, or keep the Windmill service catalog entry and controller-local secret current

The watchdog is running but stale jobs are not being aborted:
- inspect `.local/scheduler/watchdog-heartbeat.json` on the execution surface
- verify the Windmill schedule `f/lv3/scheduler_watchdog_loop_every_10s` is enabled
- confirm the target workflow appears in `config/workflow-catalog.json` with `execution_class: mutation`

Repeated watchdog aborts are occurring:
- inspect `.local/scheduler/watchdog-actions.json`
- look for `platform.findings.watchdog_repeated_action` if NATS publication is configured
- treat repeated stale-job aborts as an upstream workflow or connectivity issue, not as a normal steady state
