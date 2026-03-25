# Runbook Automation Executor

This runbook describes how ADR 0129 is represented in the repository today.

## What It Does

The runbook automation executor loads a structured runbook definition, renders each step's parameters from run-time inputs and previous step outputs, executes the referenced Windmill workflows in order, and persists the result under `.local/runbooks/runs/`.

The current implementation is repo-local:

- executor: [`scripts/runbook_executor.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/runbook_executor.py)
- CLI entrypoint: [`scripts/lv3_cli.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/lv3_cli.py) via `lv3 runbook ...`
- Windmill wrapper: [`config/windmill/scripts/runbook-executor.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/runbook-executor.py)
- persisted run records: `.local/runbooks/runs/<run_id>.json`

## Supported Definition Formats

The executor resolves runbooks from:

- YAML files under `docs/runbooks/` or `config/runbooks/`
- JSON files under `docs/runbooks/` or `config/runbooks/`
- Markdown files in those same trees when they start with YAML front matter

Minimum required fields:

```yaml
id: renew-certificate
title: Renew a service certificate
automation:
  eligible: true
steps:
  - id: check-expiry
    workflow_id: check-cert-expiry
    params:
      service: "{{ params.service }}"
    success_condition: "result.days_remaining <= 14"
```

## Templating Rules

Use `{{ ... }}` expressions inside `params`.

Available values:

- `params.<name>`: the run-time inputs passed to the executor
- `steps.<step-id>.result.<field>`: outputs from an earlier step
- `run.<field>`: persisted run metadata such as `run.run_id`

Example:

```yaml
params:
  service: "{{ params.service }}"
  previous_days: "{{ steps.check-expiry.result.days_remaining }}"
```

## Failure Strategies

Each step can declare one `on_failure` strategy:

- `escalate`: stop and persist an escalated run
- `retry_once`: retry the same step once, then escalate
- `skip`: skip a diagnostic step
- `continue`: record a warning and continue
- `rollback`: run `rollback_workflow_id`, then escalate

## Operator Entry Points

Preview a runbook:

```bash
uv run --with pyyaml python scripts/lv3_cli.py runbook execute renew-certificate --args service=grafana --dry-run
```

Execute a runbook:

```bash
uv run --with pyyaml python scripts/lv3_cli.py runbook execute renew-certificate --args service=grafana
```

Check persisted state:

```bash
uv run --with pyyaml python scripts/lv3_cli.py runbook status <run_id>
```

Resume an escalated run:

```bash
uv run --with pyyaml python scripts/lv3_cli.py runbook approve <run_id>
```

Run the repo-managed executor directly:

```bash
make runbook-executor RUNBOOK_EXECUTOR_ARGS='execute renew-certificate --param service=grafana --dry-run'
```

## Windmill Worker Path

From a worker checkout mounted at `/srv/proxmox_florin_server`:

```bash
python3 config/windmill/scripts/runbook-executor.py --repo-path /srv/proxmox_florin_server --action status --run-id <run_id>
```

## Verification

Run the focused tests:

```bash
uv run --with pytest --with pyyaml pytest tests/test_runbook_executor.py tests/test_runbook_executor_windmill.py tests/test_lv3_cli.py -q
```

Confirm the CLI preview resolves the runbook and renders the first-step inputs:

```bash
uv run --with pyyaml python scripts/lv3_cli.py runbook execute docs/runbooks/renew-certificate.yaml --args service=grafana --dry-run
```

## Notes

- Run records are repository-local state. They are intentionally not committed.
- The current implementation writes execution trace events through the mutation-audit sink.
- Markdown runbooks without automation front matter remain documentation only.
