# Observation-to-Action Closure Loop

## Purpose

ADR 0126 connects observation findings to triage, proposal, execution, and verification with a durable run record.

ADR 0204 now adds a governed correction-loop contract on top of that state machine. The authoritative catalog lives in [config/correction-loops.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0204-live-apply/config/correction-loops.json), and `make workflow-info WORKFLOW=platform-observation-loop` shows the live loop's invariant, repair order, verification source, and escalation boundary.

## Start A Run

For an operator-driven test:

```bash
lv3 loop start --trigger manual --service netbox
```

To seed an approved remediation directly:

```bash
lv3 loop start --trigger manual --service netbox --instruction "converge netbox"
```

## Inspect A Run

```bash
lv3 loop status <run_id>
```

Important fields:

- `current_state`
- `escalation_reason`
- `correction_loop`
- `verification_result`
- `history`

## Approve Or Close

If a run is paused in `ESCALATED_FOR_APPROVAL`:

```bash
lv3 loop approve <run_id> --instruction "converge netbox"
```

If the finding should be closed without automation:

```bash
lv3 loop close <run_id> --reason "false positive"
```

## Observation Wrapper

Windmill calls the wrapper at [`config/windmill/scripts/platform-observation-loop.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/windmill/scripts/platform-observation-loop.py). It:

- accepts a batch of findings
- ignores `ok` and `suppressed` items
- infers a service from the finding payload
- creates one durable loop run per actionable service finding

## Durable State

- closure-loop runs: `.local/state/closure-loop/runs.json`
- ledger events: `.local/state/ledger/ledger.events.jsonl` when running without Postgres

Each live run now records a `correction_loop` snapshot with:

- `loop_id`
- `workflow_id`
- `verification_source`
- `escalation_target`
- `retry_budget_cycles`
- `repair_action_kinds`

## Verification Rules

- workflow-specific verification uses the workflow catalog `verification` block when present
- otherwise the loop falls back to the world-state `service_health` surface
- if no probe is available, the run resolves with `verification_skipped: true`
- the current observation-loop retry budget comes from the ADR 0204 correction-loop catalog instead of a hidden hard-coded constant

## Operator Notes

- `BLOCKED` means the loop exhausted its automatic re-triage budget or hit an unsafe execution gate
- `ESCALATED_FOR_APPROVAL` means the next step is known but exceeds the current autonomous policy
- autonomous observation runs are capped to LOW-risk proposals; use `lv3 loop approve` for higher-risk remediation
- the seeded Windmill script `f/lv3/platform_observation_loop` now returns `correction_loop_id` in its JSON output so the live worker replay can prove the ADR 0204 contract is active
