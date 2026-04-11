# Agent Capability Policy

## Purpose

This runbook documents ADR 0125 and the repo-managed policy that bounds what each automation identity may read, execute autonomously, or escalate.

## Canonical Surfaces

- `config/agent-policies.yaml`
- `platform/agent_policy/`
- `platform/goal_compiler/`
- `platform/scheduler/`
- `scripts/lv3_cli.py`

## Policy Model

Each policy entry defines:

- `agent_id`: the durable runtime identity
- `identity_class`: `service-agent` or `operator-agent`
- `trust_tier`: `T1` through `T4`
- `read_surfaces`: named read surfaces the actor may depend on
- `autonomous_actions`: risk ceiling, allowed workflow tags, disallowed workflow IDs, and the daily autonomous cap
- `escalation`: where a bounded action is sent when autonomy is insufficient

Workflow classes are matched through catalog tags:

- `diagnostic` for read-only or check-style workflows
- `converge` for repo-managed reconciliation workflows
- `rotate_secret` for bounded secret rotation workflows
- `validation` for repo validation flows
- `auto_check` for triage-triggered checks

## Operator Usage

`lv3 run` now accepts:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
python3 scripts/lv3_cli.py run deploy netbox --actor-id operator:lv3-cli
```

To simulate or run unattended agent mode:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
python3 scripts/lv3_cli.py run validate --actor-id agent/triage-loop --autonomous
```

If an autonomous action is outside bounds, the compiler or scheduler rejects it with one of:

- `CAPABILITY_DENIED`
- `CAPABILITY_ESCALATION_REQUIRED`
- `daily_autonomous_limit_reached`

## Adding Or Changing A Policy

1. Edit `config/agent-policies.yaml`.
2. If the actor needs a new workflow class, add or update the workflow's `tags` and `required_read_surfaces` in `config/workflow-catalog.json`.
3. Run `python3 scripts/validate_repository_data_models.py --validate`.
4. Run the focused unit tests for the goal compiler, scheduler, and CLI policy paths.

## Daily Autonomous Cap

The scheduler records autonomous submission counts in the repo-local fallback file:

- `.local/state/agent-policy/daily-autonomous-executions.json`

The counter is keyed by UTC date. Manual operator-approved runs do not consume the cap.

## Verification

1. `python3 scripts/validate_repository_data_models.py --validate`
2. `pytest tests/unit/test_agent_policy.py tests/unit/test_goal_compiler.py tests/unit/test_scheduler_budgets.py tests/test_lv3_cli.py -q`
3. `python3 scripts/lv3_cli.py run validate --actor-id agent/triage-loop --autonomous --dry-run`
4. `python3 scripts/lv3_cli.py run deploy netbox --actor-id agent/triage-loop --autonomous`

The last command should fail with a capability-bound rejection.
