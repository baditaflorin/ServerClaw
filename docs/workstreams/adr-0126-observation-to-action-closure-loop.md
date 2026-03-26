# Workstream ADR 0126: Observation-To-Action Closure Loop

- ADR: [ADR 0126](../adr/0126-observation-to-action-closure-loop.md)
- Title: Durable loop that carries one finding through triage, proposal, execution, verification, and operator escalation
- Status: live_applied
- Branch: `codex/adr-0126-logic-loop-clean`
- Worktree: `../proxmox_florin_server-adr-0126-logic-loop-clean`
- Owner: codex
- Depends On: `adr-0048-command-catalog`, `adr-0064-health-probe-contracts`, `adr-0071-agent-observation-loop`, `adr-0090-platform-cli`, `adr-0112-goal-compiler`, `adr-0114-incident-triage`, `adr-0115-mutation-ledger`, `adr-0119-budgeted-workflow-scheduler`
- Conflicts With: `adr-0112-goal-compiler`, `adr-0114-incident-triage`, `adr-0119-budgeted-workflow-scheduler`
- Shared Surfaces: `platform/closure_loop/`, `config/windmill/scripts/platform-observation-loop.py`, `scripts/lv3_cli.py`, `config/workflow-catalog.json`, `config/ledger-event-types.yaml`

## Scope

- create `platform/closure_loop/` with durable state storage and the ADR 0126 state machine
- update `config/windmill/scripts/platform-observation-loop.py` so observation findings create loop runs instead of returning a summary stub
- update `scripts/lv3_cli.py` with `lv3 loop start|status|approve|close`
- add repo-local policy defaults in `config/agent-policies.yaml`
- add loop transition and escalation event types to `config/ledger-event-types.yaml`
- document the runtime and operations flow in ADR and runbook form
- cover auto-check, approval, verification, and termination paths with tests

## Non-Goals

- Full ADR 0127 resource-claim conflict detection
- Full ADR 0128 composite health index
- Automatic case-library promotion beyond durable resolution recording

## Expected Repo Surfaces

- `platform/closure_loop/__init__.py`
- `platform/closure_loop/engine.py`
- `platform/closure_loop/store.py`
- `config/agent-policies.yaml`
- `config/windmill/scripts/platform-observation-loop.py`
- `config/workflow-catalog.json`
- `config/ledger-event-types.yaml`
- `scripts/lv3_cli.py`
- `docs/adr/0126-observation-to-action-closure-loop.md`
- `docs/runbooks/observation-to-action-closure-loop.md`
- `docs/workstreams/adr-0126-observation-to-action-closure-loop.md`

## Verification

- run `pytest tests/unit/test_closure_loop.py tests/test_closure_loop_windmill.py tests/test_lv3_cli.py -q`
- run `python3 config/windmill/scripts/platform-observation-loop.py --repo-path .`
- run `python3 scripts/lv3_cli.py loop start --trigger manual --service netbox`
- run the repo-managed `scripts/sync_windmill_seed_scripts.py` helper against the production Windmill API from the rebased current-main checkout
- run `POST /api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fplatform_observation_loop` with a critical service-health finding and confirm the live Windmill wrapper returns structured loop output
- run a live `observation_finding` closure-loop start on `docker-runtime-lv3` with `goal_achieved: true` and confirm the state machine stops at `RESOLVED`

## Merge Criteria

- loop run records are durable across process restarts
- auto-check findings advance through VERIFYING and terminate on goal achievement
- paused runs can be approved or closed from the CLI
- ledger transition events are emitted for each state change

## Outcome

- repository implementation is complete on `main` in repo release `0.131.0`
- the closure loop now terminates explicitly when triage or verification proves the service goal is already satisfied
- observation findings can now create durable runs through Windmill and be inspected or approved through `lv3 loop`
- production activation is recorded in `receipts/live-applies/2026-03-26-adr-0126-observation-to-action-closure-loop-live-apply.json`
- the Windmill script seed path now uses a dedicated repo-managed helper because the raw API delete/create sequence was not reliable enough during live reseeds

## Notes For The Next Assistant

- the first implementation deliberately uses current repo surfaces for policy, conflict, and health rather than waiting on ADRs 0125, 0127, and 0128
- if ADR 0127 lands later, replace the service-scoped conflict guard with resource claims before widening autonomous remediation
