# Windmill schedule templates

Declarative schedule descriptors that the Windmill operator imports
into the live workspace. Each YAML file under this directory describes
one recurring task: what to run, on what cadence, what to do with the
result.

The files are NOT live Windmill state — they're version-controlled
templates. The live cron lives in the Windmill workspace and is
created by an operator running `wmill schedule` against the descriptor.
This separation lets the recurring-task contract be reviewed in a PR
without granting the worktree write access to Windmill.

## Schema (informal, v1)

```yaml
schema_version: 1
schedule_id:    <unique kebab-case id>
adr:            <ADR number that introduced this schedule>
description:    <one-paragraph purpose>
cadence:
  cron:         <standard 5-field cron expression in UTC>
  timezone:     UTC
runner:
  type:         python_script | bash | playbook
  path:         <repo-relative or wmill workspace path>
  args:         [list of args]
on_signal:
  - condition:  <jq-style predicate over the runner's output>
    action:     <plane_issue | slack_post | ops_portal_widget | ...>
    target:     <where to send>
ownership:
  workstream:   <ws-NNNN id>
  contact:      <who pages on failure>
```

## Adding a schedule

1. Drop a new `<id>.yaml` in this directory using the schema above.
2. Open a PR with the workstream that owns the schedule.
3. After merge, the operator with Windmill access imports it via
   `wmill schedule create -f config/windmill/schedules/<id>.yaml`.

## Activation tracker

| schedule_id | adr | active in workspace? | activated_on |
|---|---|---|---|
| `refresh-safe-receipts` | 0450 | NO — pending operator import | — |
