# ADR 0090: Unified Platform CLI (`lv3`)

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.91.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

As the platform matures, the number of `make` targets, scripts, Windmill workflows, and runbooks has grown substantially. The current surface for an operator wanting to do any common task is:

- ~60 `make` targets in a monolithic `Makefile`
- `scripts/*.py` called directly with varying argument conventions
- Windmill UI for triggering workflows
- Manual `ansible-playbook` invocations with long flag strings
- Separate `tofu` commands with environment flags
- SSH commands to individual VMs

This creates a **discoverability problem**: a new operator (or the same operator after a month away) cannot answer "what command do I run to deploy a new service?" without reading multiple runbooks. The Makefile is not self-documenting beyond `make help`, and `make help` lists all 60 targets with one-line descriptions but no grouping, workflow guidance, or context about where each command actually runs (local vs build server vs Windmill vs VM).

The ops portal (ADR 0074) addresses the *browser* experience. This ADR addresses the *terminal* experience: a single `lv3` CLI that is the authoritative entry point for all common operator tasks.

## Decision

We will implement a `lv3` CLI tool at `scripts/lv3_cli.py`, installed as `lv3` in the operator's `PATH` via `make install-cli`.

### Design principles

1. **Human-first**: `lv3 deploy grafana` is more discoverable than `make remote-exec PLAYBOOK=site.yml TAGS=grafana ENV=production`
2. **Transparent routing**: each command tells the operator where it will run before running it (local, build server, Windmill, remote VM)
3. **Consistent output**: all commands produce structured terminal output with timing, exit status, and a receipt URL
4. **No hidden behaviour**: `lv3 <cmd> --dry-run` shows what would happen without doing it; `lv3 <cmd> --explain` shows the underlying `make`/`ansible`/`tofu` command

### Command groups

```
lv3 deploy <service> [--env staging|production] [--dry-run]
lv3 lint [--local]
lv3 validate [--strict]
lv3 status [<service>]
lv3 vm <create|destroy|resize|list> [args]
lv3 secret <get|rotate> <path>
lv3 fixture <up|down> <fixture-name>
lv3 scaffold <service-name>
lv3 diff [--env staging|production]
lv3 promote <adr-branch> --service <service> --staging-receipt <receipt> [--to staging|production]
lv3 run <windmill-workflow> [--args key=val]
lv3 logs <service> [--tail N]
lv3 ssh <vm-name>
lv3 open <service>
```

### Command routing table

| Command | Routes to | Where |
|---|---|---|
| `lv3 deploy` | `make remote-exec COMMAND="make live-apply-service ..."` | build server → Proxmox VM |
| `lv3 lint` | `make remote-lint` or `scripts/validate_repo.sh yaml ansible-lint` | build server (or local with `--local`) |
| `lv3 validate` | `make remote-validate` or `make remote-pre-push` with `--strict` | build server |
| `lv3 vm create` | repo-managed OpenTofu route via `make remote-tofu-apply ...` or a guarded `remote-exec` fallback | build server → Proxmox API |
| `lv3 secret get` | `openbao kv get ...` (over Tailscale) | OpenBao on `docker-runtime` |
| `lv3 fixture up` | `make fixture-up FIXTURE=...` | build server → Proxmox staging |
| `lv3 run` | Windmill API trigger | Windmill on `docker-runtime` |
| `lv3 logs` | Loki API query | Loki on monitoring VM |
| `lv3 ssh` | `ssh ops@<inventory-ip>` | direct SSH via Tailscale / subnet route |
| `lv3 open` | `python3 -m webbrowser <url>` | local browser |

### Implementation

`scripts/lv3_cli.py` is a Python 3.12 script with no runtime dependencies beyond the standard library. It reads:
- `config/service-capability-catalog.json` for service URLs, health probes, VM assignments
- `config/health-probe-catalog.json` for status probing rules
- `config/workflow-catalog.json` for Windmill workflow discovery and completion
- `config/controller-local-secrets.json` for local secret file locations used by private API routes

The CLI is self-bootstrapping: `lv3 --help` works immediately after `make install-cli`; it does not require Ansible, Docker, or any service to be reachable.

Routes that depend on other ADRs such as OpenTofu VM lifecycle, fixtures, or service scaffolding fail explicitly when the required repo surfaces are still absent. The CLI does not invent ad hoc fallbacks for missing automation.

### `make install-cli`

```bash
pipx install --editable . --force  # installs lv3 CLI from pyproject.toml
# fallback when pipx is unavailable:
python3 -m pip install --user --editable .
```

### Shell completion

```bash
lv3 --install-completion bash   # writes to ~/.bashrc
lv3 --install-completion zsh    # writes to ~/.zshrc
```

### Output format example

```
$ lv3 deploy grafana --env staging

lv3 deploy grafana --env staging
Route:   controller -> build server -> target service playbook
Command: make remote-exec COMMAND='make live-apply-service service=grafana env=staging'

Exit:    0

Receipt: receipts/live-applies/<latest-matching-receipt>.json
Total:   1m 46s
```

### `lv3 status` — the dashboard in a terminal

```
$ lv3 status

PLATFORM STATUS  (example.com)                          2026-03-22 09:41 UTC
───────────────────────────────────────────────────────────────────────
SERVICE             VM                    URL                     HEALTH
grafana             monitoring        grafana.example.com         ✓ 200
prometheus          monitoring        —                       ✓ live
openbao             docker-runtime    —                       ✓ live
windmill            docker-runtime    windmill.example.com        ✓ 200
keycloak            docker-runtime    auth.example.com            ✓ 200
...

LAST DEPLOY         2026-03-23-<receipt>
```

## Consequences

**Positive**
- New operators can be productive in minutes: `lv3 --help` describes everything; `lv3 open ops` shows the ops portal
- `lv3 lint`, `lv3 validate`, `lv3 deploy` replace ~20 `make` targets with memorable verb-noun commands
- Routing transparency eliminates "wait, does this run on my laptop?" confusion
- Shell completion makes the CLI pleasant to use; the 30+ commands become browsable
- `--dry-run` and `--explain` on every command lower the fear barrier for new operators
- The CLI can expose future routes early while still failing explicitly if a dependent ADR surface is not merged yet

**Negative / Trade-offs**
- The CLI is a thin wrapper; it does not add new capabilities, only a consistent surface over existing ones
- Must be kept in sync with the underlying `make` targets and scripts; a `make` target rename requires a CLI update
- Some command groups are only as complete as the underlying ADRs they depend on; the CLI surfaces those dependency gaps rather than hiding them

## Alternatives Considered

- **Just improve `make help`**: does not solve routing transparency or verb-noun discoverability
- **A Go CLI binary**: faster startup, distributable binary; higher development friction for a Python-native team; deferred to a future ADR if startup time becomes a concern
- **Taskfile (go-task)**: YAML-based task runner; better than Make but still not human-verb-oriented; does not address routing transparency

## Related ADRs

- ADR 0074: Ops portal (browser companion to the terminal experience)
- ADR 0075: Service capability catalog (data source for `lv3 status` and `lv3 open`)
- ADR 0082: Remote build execution gateway (`lv3 lint`, `lv3 validate`, `lv3 deploy` route through this)
- ADR 0085: OpenTofu VM lifecycle (`lv3 vm create` calls `make remote-tofu-apply`)
- ADR 0078: Service scaffold generator (`lv3 scaffold` wraps `make scaffold-service`)
