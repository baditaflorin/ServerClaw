# Budgeted Workflow Scheduler

## Purpose

ADR 0119 inserts a repository-managed scheduler between `lv3 run` and Windmill. The scheduler loads per-workflow budgets, enforces concurrency and rollback-depth guards, and runs a watchdog over active mutation jobs.

ADR 0172 extends that watchdog so it can also:

- discover running mutation jobs directly from Windmill
- abort stale jobs after `90` seconds without observed activity
- emit a repeated-action finding after three identical self-healing actions in ten minutes
- write `.local/scheduler/watchdog-heartbeat.json` on every tick

ADR 0157 adds per-lane resource reservations. Mutation workflows now declare CPU, memory, disk-I/O, and duration estimates; the scheduler admits or rejects execution against the VM budget defined in `config/execution-lanes.yaml`.

## Canonical Sources

- scheduler package: [platform/scheduler](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/scheduler)
- workflow defaults: [config/workflow-defaults.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-defaults.yaml)
- workflow catalog budgets: [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json)
- execution lanes: [config/execution-lanes.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/execution-lanes.yaml)
- watchdog entry point: [windmill/scheduler/watchdog-loop.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/windmill/scheduler/watchdog-loop.py)
- Windmill seed defaults: [collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml)
- timeout hierarchy: [config/timeout-hierarchy.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/timeout-hierarchy.yaml)

## Operator Paths

Interactive workflow execution now routes through the scheduler:

```bash
lv3 run converge-netbox
```

Run one watchdog pass locally:

```bash
uv run --with pyyaml python windmill/scheduler/watchdog-loop.py --repo-path .
```

Run one controller-side Windmill script probe through the same `jobs/run_wait_result` contract used for live verification:

```bash
WINDMILL_TOKEN="$(cat .local/windmill/superadmin-secret.txt)" \
python3 scripts/windmill_run_wait_result.py \
  --base-url http://100.64.0.1:8005 \
  --workspace lv3 \
  --path f/lv3/windmill_healthcheck \
  --payload-json '{"probe":"live-verify"}'
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

Inspect one execution lane budget:

```bash
make execution-lane-info LANE=lane:docker-runtime
```

## Budget Model

- `config/workflow-defaults.yaml` defines the baseline budget applied when a workflow does not override a field.
- `config/workflow-defaults.yaml` also defines the default mutation `resource_reservation`.
- `config/workflow-catalog.json` can override any budget field per workflow, declares `execution_class`, and can set `target_lane` plus per-workflow `resource_reservation`.
- `config/execution-lanes.yaml` defines the VM-level concurrency budgets and whether over-budget submissions are `hard` rejected or `soft` admitted with warnings.
- `config/timeout-hierarchy.yaml` defines the outer timeout ceilings and defaults used by the scheduler, gateway, world-state workers, and the live watchdog seed path.
- Only `execution_class: mutation` workflows are subject to scheduler budget enforcement.
- Host-touch limits are advisory in this first implementation unless the workflow supplies an explicit host list in its input arguments.

## State And Locks

- Active jobs are tracked in `.local/scheduler/active-jobs.json`.
- The watchdog also queries Windmill for running jobs so the scheduled loop can operate without sharing the controller-local state file.
- Active lane reservations are tracked in `.local/scheduler/lane-reservations.json`.
- Concurrency uses Postgres advisory transaction locks when `LV3_LEDGER_DSN` is present.
- Without a ledger DSN, the scheduler falls back to repo-local file locks under `.local/scheduler/locks/`.
- The watchdog heartbeat is written to `.local/scheduler/watchdog-heartbeat.json`.
- Recent self-healing actions are tracked in `.local/scheduler/watchdog-actions.json`.
- Windmill worker helpers first look for `LV3_WINDMILL_BASE_URL` and `LV3_WINDMILL_TOKEN` in the rendered runtime env, then fall back to `/proc/1/environ`, then to `/srv/proxmox_florin_server/.local/windmill/superadmin-secret.txt` on the mirrored worker checkout.

## Live Verification

- 2026-03-27 latest-main live verification confirmed `f/lv3/windmill_healthcheck`, `f/lv3/intent_queue_dispatcher`, `f/lv3/lane_scheduler`, `f/lv3/scheduler_watchdog`, and `f/lv3/scheduler_watchdog_loop` all returned `status: ok` through `jobs/run_wait_result`.
- The enabled scheduler surfaces were rechecked after the latest-main replay: `f/lv3/intent_queue_dispatcher_every_minute`, `f/lv3/lane_scheduler_every_2s`, `f/lv3/scheduler_watchdog_every_30s`, and `f/lv3/scheduler_watchdog_loop_every_10s`.
- The live Windmill API script bodies for `f/lv3/intent_queue_dispatcher`, `f/lv3/lane_scheduler`, `f/lv3/scheduler_watchdog`, and `f/lv3/scheduler_watchdog_loop` now match the checked-in branch sources byte-for-byte after the duplicate seed-path contract was removed from the Windmill defaults.
- The worker runtime env on `docker-runtime-lv3` now includes `LV3_WINDMILL_BASE_URL` and `LV3_WINDMILL_TOKEN`, and the mirrored worker secret file exists at `/srv/proxmox_florin_server/.local/windmill/superadmin-secret.txt`.

## Troubleshooting

`lv3 run ...` returns `concurrency_limit`:
- another instance of the same mutation workflow is already active
- confirm with `.local/scheduler/active-jobs.json`

`lv3 run ...` returns `budget_exceeded` with `lane_budget_exceeded`:
- inspect `config/execution-lanes.yaml` and `config/workflow-catalog.json`
- check `.local/scheduler/lane-reservations.json` for active reservations and their TTLs
- if the lane uses `admission_policy: soft`, expect execution to continue with a warning in the scheduler result metadata instead of a hard rejection

`lv3 run ...` returns `rollback_depth_exceeded`:
- the supplied `parent_actor_intent_id` chain already exceeds the budgeted rollback depth
- inspect `ledger.events` for the prior scheduler lifecycle records

`uv run --with pyyaml python windmill/scheduler/watchdog-loop.py --repo-path .` returns `blocked`:
- verify the repo checkout path exists on the worker
- export `LV3_WINDMILL_BASE_URL` and `LV3_WINDMILL_TOKEN`, or keep the Windmill service catalog entry and controller-local secret current

The Windmill runtime apply passes manual `jobs/run_wait_result` probes but the role-level healthcheck still needs investigation:
- run the controller-side helper above directly to confirm whether Windmill itself is healthy
- compare the direct helper result against the Ansible task path in `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- treat the current replay failure as an automation wrapper issue until the direct helper also fails

The watchdog is running but stale jobs are not being aborted:
- inspect `.local/scheduler/watchdog-heartbeat.json` on the execution surface
- verify the Windmill schedule `f/lv3/scheduler_watchdog_loop_every_10s` is enabled
- confirm the target workflow appears in `config/workflow-catalog.json` with `execution_class: mutation`

Repeated watchdog aborts are occurring:
- inspect `.local/scheduler/watchdog-actions.json`
- look for `platform.findings.watchdog_repeated_action` if NATS publication is configured
- treat repeated stale-job aborts as an upstream workflow or connectivity issue, not as a normal steady state
