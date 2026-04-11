# Platform CLI

## Purpose

`lv3` is the terminal entry point for common operator tasks in this repository.

It wraps the existing make targets, service catalog, workflow catalog, and controller-local secret references behind one discoverable command surface.

## Installation

Preferred:

```bash
make install-cli
```

This installs the editable CLI entry point into the current operator environment.

Update an existing install after changes:

```bash
make update-cli
```

Install completion:

```bash
lv3 --install-completion bash
lv3 --install-completion zsh
```

## Core Commands

Show the full command surface:

```bash
lv3 --help
```

Check repository health:

```bash
lv3 lint
lv3 validate
lv3 validate --strict
```

Inspect platform health:

```bash
lv3 status
lv3 status grafana
```

Preview a deploy route without executing it:

```bash
lv3 deploy grafana --env production --dry-run
```

Open a published or private operator surface:

```bash
lv3 open ops_portal
lv3 open windmill
```

Inspect logs through Loki:

```bash
lv3 logs windmill --tail 50 --since 2h
```

Compile and execute a platform instruction through the goal compiler:

```bash
lv3 run deploy netbox --dry-run
lv3 run rotate secret for grafana --args reason=manual
lv3 run windmill_healthcheck --args probe=manual
```

Inspect release readiness and prepare a repository release:

```bash
lv3 release status
lv3 release --bump patch --dry-run
```

## Routing Model

- `lv3 lint` and `lv3 validate` route through ADR 0082's build-server gateway unless `--local` is set.
- `lv3 deploy` routes to `make remote-exec` and then into the repo-managed service apply path.
- `lv3 status`, `lv3 logs`, and `lv3 open` use catalog-backed read paths from the controller.
- `lv3 run` compiles the workflow intent, enforces ADR 0116 risk gates, then submits through ADR 0119's budgeted scheduler before the Windmill API call is made.
- `lv3 release` reads repository metadata and release receipts locally; `lv3 release tag` shells out to git for the annotated tag step.

## Current Limits

- `lv3 vm create`, `lv3 vm destroy`, `lv3 diff`, and `lv3 fixture ...` assume the related OpenTofu and fixture workstreams are present on the execution surface. If those repo surfaces are still missing, the CLI fails explicitly instead of silently guessing.
- `lv3 scaffold` expects ADR 0078's `make scaffold-service` surface. If that generator is not merged yet, the command will fail through the underlying make target.
- `lv3 deploy` follows ADR 0090's build-server route, so the remote execution surface must already have the required live-apply prerequisites.
- `lv3 run` only executes instructions that resolve to a known workflow route. Unmatched instructions return `PARSE_ERROR` and do not mutate anything.

## Troubleshooting

`lv3 lint` or `lv3 validate` fails before running:
- run `make check-build-server`

`lv3 status` shows timeouts:
- verify the operator machine still has the Proxmox Tailscale route for `10.10.10.0/24`

`lv3 run ...` cannot authenticate:
- verify `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/windmill/superadmin-secret.txt` exists and is current

`lv3 run ...` returns `PARSE_ERROR`:
- inspect the compiled rule set in `config/goal-compiler-rules.yaml`
- add or refine aliases in `config/goal-compiler-aliases.yaml` when the intent is valid but phrased differently
- confirm the target service or workflow exists in the relevant repo catalog before widening the rule table

`lv3 run ...` returns `concurrency_limit` or `budget_exceeded`:
- inspect `config/workflow-catalog.json` and `config/workflow-defaults.yaml`
- run `make scheduler-watchdog-loop` to reconcile active scheduler state

`lv3 logs ...` cannot reach Loki:
- override the query endpoint with `LV3_LOKI_URL=http://<host>:3100/loki/api/v1/query_range`
