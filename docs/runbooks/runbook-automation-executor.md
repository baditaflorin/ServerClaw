# Runbook Automation Executor

This runbook describes how ADR 0129 is represented in the repository today.

## What It Does

The runbook automation executor loads a structured runbook definition, renders each step's parameters from run-time inputs and previous step outputs, executes the referenced Windmill workflows in order, and persists the result under `.local/runbooks/runs/`.

The current implementation now shares one use-case service across multiple delivery adapters:

- shared orchestration: [`platform/use_cases/runbooks.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/use_cases/runbooks.py)
- CLI adapter: [`scripts/runbook_executor.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/runbook_executor.py)
- CLI entrypoint: [`scripts/lv3_cli.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/lv3_cli.py) via `lv3 runbook ...`
- Windmill wrapper: [`config/windmill/scripts/runbook-executor.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/runbook-executor.py)
- API gateway adapter: [`scripts/api_gateway/main.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/api_gateway/main.py)
- ops portal adapter: [`scripts/ops_portal/app.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/ops_portal/app.py)
- persisted run records:
  - CLI and worker checkouts: `.local/runbooks/runs/<run_id>.json`
  - API gateway runtime: `/data/runbooks/runs/<run_id>.json`

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
  delivery_surfaces:
    - cli
    - windmill
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

## Delivery Surfaces

Structured runbooks can now opt into specific adapters with `automation.delivery_surfaces`.

If the field is omitted, the default surface allowlist is:

- `cli`
- `windmill`

Additional supported surfaces are:

- `api_gateway`
- `ops_portal`

Example:

```yaml
automation:
  eligible: true
  delivery_surfaces:
    - api_gateway
    - cli
    - ops_portal
    - windmill
```

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

List the API-gateway-exposed runbooks:

```bash
curl -sS http://100.64.0.1:8083/v1/platform/runbooks \
  -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/platform-context/api-token.txt)"
```

Execute the safe gateway verification runbook:

```bash
curl -sS http://100.64.0.1:8083/v1/platform/runbooks/execute \
  -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/platform-context/api-token.txt)" \
  -H "Content-Type: application/json" \
  -d '{"runbook_id":"validation-gate-status"}'
```

When verifying from an SSH shell on `docker-runtime-lv3`, use the guest-local listeners instead of the Proxmox host proxy:

- API gateway: `http://127.0.0.1:8083`
- Windmill: `http://127.0.0.1:8000`

The `http://100.64.0.1:8005` Windmill endpoint is the Proxmox host Tailscale proxy and is not expected to listen on the guest loopback.

## Windmill Worker Path

From a worker checkout mounted at `/srv/proxmox_florin_server`:

```bash
python3 config/windmill/scripts/runbook-executor.py --repo-path /srv/proxmox_florin_server --action status --run-id <run_id>
```

## Verification

Run the focused tests:

```bash
uv run --with pytest --with pyyaml --with httpx --with cryptography --with fastapi --with jinja2 --with itsdangerous --with python-multipart pytest tests/test_runbook_executor.py tests/test_runbook_executor_windmill.py tests/test_api_gateway.py tests/test_interactive_ops_portal.py tests/test_lv3_cli.py -q
```

Confirm the CLI preview resolves the runbook and renders the first-step inputs:

```bash
uv run --with pyyaml python scripts/lv3_cli.py runbook execute docs/runbooks/renew-certificate.yaml --args service=grafana --dry-run
```

## Notes

- Run records are repository-local state. They are intentionally not committed.
- The shared use-case service writes execution trace events through the mutation-audit sink, while each adapter keeps only transport-specific parsing and rendering.
- `docs/runbooks/validation-gate-status.yaml` is the preferred safe verification path for the API gateway and ops portal adapters.
- Markdown runbooks without automation front matter remain documentation only.
