# ADR 0172: Watchdog Escalation and Stale Job Self-Healing

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.143.2
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

ADR 0119 added a budgeted scheduler and a watchdog loop, but the watchdog still had two practical gaps on `main`:

- it only enforced duration, step, and touched-host budgets for jobs already tracked in the local scheduler state file
- it had no durable self-healing escalation path or liveness signal of its own

That left an obvious failure mode: a Windmill job could still be `running`, emit no useful progress for a long stretch, and continue to hold the mutation lane until the outer duration budget finally expired. The platform also lacked an explicit heartbeat proving that the watchdog loop itself was still executing.

## Decision

We extend the scheduler watchdog into a stale-job backstop that can operate from repo-managed Windmill schedules as well as local controller runs.

The implementation has five parts:

1. `platform/scheduler/watchdog.py` now detects stale mutation jobs by last observed activity, not only by total elapsed duration.
2. The watchdog can discover running jobs directly from the Windmill jobs API, so the live loop is no longer limited to the local `active-jobs.json` file.
3. Every destructive watchdog action records a durable action-history entry and emits a repeated-action finding after three identical self-healing actions within ten minutes.
4. Every watchdog tick writes a heartbeat file under `.local/scheduler/watchdog-heartbeat.json` and publishes a `platform.watchdog.heartbeat` event when NATS credentials are configured.
5. The Windmill runtime now seeds and enables a repo-managed `f/lv3/scheduler_watchdog_loop` script on a ten-second schedule.

## Implementation Notes

### Stale-job detection

The watchdog now treats a mutation job as stale when:

- the job is still running
- the last observable activity timestamp is older than `90` seconds
- the job has not already reached a terminal state

Activity timestamps are derived conservatively from Windmill status fields such as:

- `last_log_at`
- `updated_at`
- `last_progress_at`
- nested `flow_status` timestamps

If the watchdog aborts a stale job, it writes:

- `execution.stale_job_detected`
- `execution.aborted`

and emits `platform.watchdog.stale_job_aborted` when an escalation publisher is available.

### Remote discovery

`HttpWindmillClient` now supports `list_jobs(running=True)`. The watchdog uses that to reconstruct mutation job records from live Windmill jobs by normalizing script paths such as:

- `f/lv3/converge_netbox`
- `f/lv3/deploy_and_promote`

back to workflow-catalog ids like:

- `converge-netbox`
- `deploy-and-promote`

This lets the scheduled Windmill watchdog observe live jobs even when the controller that submitted them is not sharing a local scheduler state file with the worker.

### Repeated-action escalation

Watchdog self-healing actions are written into `.local/scheduler/watchdog-actions.json`. When the same action type reaches three events inside a rolling ten-minute window, the watchdog emits `platform.findings.watchdog_repeated_action` so the operator sees a systemic problem instead of a stream of isolated cancels.

### Heartbeat

Every tick writes `.local/scheduler/watchdog-heartbeat.json` with:

- the tick timestamp
- active and completed job counts
- violation and warning counts
- the configured poll interval

This is the repo-managed liveness surface for the watchdog itself.

## Consequences

### Positive

- a silent running mutation job is now aborted after ninety seconds of inactivity instead of waiting only on the outer duration budget
- the live watchdog loop can discover mutation jobs from Windmill directly
- repeated self-healing actions now escalate instead of failing quietly
- operators have a concrete heartbeat artifact to inspect on the runtime host

### Trade-offs

- stale detection is still heuristic and depends on Windmill exposing a useful activity timestamp
- the scheduled watchdog loop remains a separate backstop; it does not replace in-process timeout handling from ADR 0170
- the heartbeat is emitted and persisted now, but full health-catalog wiring for a dedicated `platform-watchdog` service remains a future topology change

## Boundaries

- This ADR governs scheduler- and Windmill-level mutation jobs only. It does not restart arbitrary application processes inside guests.
- This implementation does not yet repair future lock-registry, intent-queue, or abandoned-session state because those shared runtime surfaces are not present on `main`.
- The watchdog still applies only to `execution_class: mutation` workflows.

## Related ADRs

- ADR 0044: Windmill
- ADR 0115: Event-sourced mutation ledger
- ADR 0119: Budgeted workflow scheduler
