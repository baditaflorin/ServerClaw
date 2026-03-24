# Workstream ADR 0125: Agent Capability Bounds

- ADR: [ADR 0125](../adr/0125-agent-capability-bounds-and-autonomous-action-policy.md)
- Title: Repo-managed policy that bounds each automation identity's read surfaces, autonomous workflow classes, risk ceiling, and escalation path before a workflow can run
- Status: merged
- Branch: `codex/adr-0125-agent-capability-bounds`
- Worktree: `.worktrees/adr-0125`
- Owner: codex
- Depends On: `adr-0046-identity-classes`, `adr-0069-agent-tool-registry`, `adr-0112-goal-compiler`, `adr-0119-budgeted-workflow-scheduler`
- Conflicts With: `adr-0112-goal-compiler` (shared compile path), `adr-0119-budgeted-workflow-scheduler` (shared submission path)
- Shared Surfaces: `platform/agent_policy/`, `platform/goal_compiler/`, `platform/scheduler/`, `config/agent-policies.yaml`, `config/workflow-catalog.json`, `scripts/lv3_cli.py`

## Scope

- add the canonical `config/agent-policies.yaml` policy registry
- add `platform/agent_policy/` with policy loading, workflow-tag resolution, and repo-local daily autonomous counters
- enforce policy bounds in the goal compiler before natural-language intents are accepted for autonomous execution
- enforce workflow-tag, surface, risk-ceiling, and daily autonomous-cap bounds in the scheduler for direct workflow execution too
- expose the policy path through `lv3 run --actor-id ... --autonomous`
- validate the new config and document the operator flow

## Non-Goals

- replacing Keycloak or command-catalog approval policy
- runtime widening of an agent policy outside git
- designing the final operator approval UX in the interactive ops portal

## Expected Repo Surfaces

- `config/agent-policies.yaml`
- `platform/agent_policy/`
- `platform/goal_compiler/compiler.py`
- `platform/scheduler/scheduler.py`
- `scripts/lv3_cli.py`
- `scripts/validate_repository_data_models.py`
- `scripts/workflow_catalog.py`
- `docs/runbooks/agent-capability-policy.md`

## Expected Live Surfaces

- none yet; this change is repo-integrated and ready for later live consumers

## Verification

- `python3 scripts/validate_repository_data_models.py --validate`
- `pytest tests/unit/test_agent_policy.py tests/unit/test_goal_compiler.py tests/unit/test_scheduler_budgets.py tests/test_lv3_cli.py -q`
- confirm `lv3 run deploy netbox --actor-id agent/triage-loop --autonomous` rejects the action before execution

## Merge Criteria

- policy file validates
- goal compiler rejects or escalates bounded autonomous actions
- scheduler rejects direct out-of-bounds workflow submissions
- daily autonomous cap is enforced with tests

## Notes For The Next Assistant

- workflow tags are inferred from workflow IDs and execution class, but explicit `tags` in `config/workflow-catalog.json` win when a workflow needs a narrower classification
- the current daily autonomous counter uses a repo-local JSON fallback; a future live rollout can swap in the Postgres-backed store without changing the policy contract
