# ADR 0090: Unified Platform CLI (`lv3`)

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
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
lv3 lint [--fix] [--local]
lv3 validate [--strict]
lv3 status [<service>]
lv3 vm <create|destroy|resize|list> [args]
lv3 secret <get|rotate> <path>
lv3 fixture <up|down> <fixture-name>
lv3 scaffold <service-name>
lv3 diff [--env staging|production]
lv3 promote <adr-branch> [--to staging|production]
lv3 run <windmill-workflow> [--args key=val]
lv3 logs <service> [--tail N]
lv3 ssh <vm-name>
lv3 open <service>
```

### Command routing table

| Command | Routes to | Where |
|---|---|---|
| `lv3 deploy` | `make remote-exec PLAYBOOK=...` | build server → Proxmox VM |
| `lv3 lint` | `make remote-lint` or `make lint` | build server (or local with `--local`) |
| `lv3 validate` | `make remote-validate` | build server |
| `lv3 vm create` | `make remote-tofu-apply ENV=...` | build server → Proxmox API |
| `lv3 secret get` | `openbao kv get ...` (over Tailscale) | OpenBao on `docker-runtime-lv3` |
| `lv3 fixture up` | `make fixture-up FIXTURE=...` | build server → Proxmox staging |
| `lv3 run` | Windmill API trigger | Windmill on `docker-runtime-lv3` |
| `lv3 logs` | Loki API query | Loki on monitoring VM |
| `lv3 ssh` | `ssh ops@<tailscale-ip>` | direct SSH via Tailscale |
| `lv3 open` | `open https://<service>.lv3.org` | local browser |

### Implementation

`scripts/lv3_cli.py` is a Python 3.12 script with no external dependencies beyond the stdlib and `click` (already in `requirements.txt`). It reads:
- `config/service-capability-catalog.json` for service URLs, health probes, VM assignments
- `config/build-server.json` for remote execution config
- `config/vm-template-manifest.json` for Packer template state

The CLI is self-bootstrapping: `lv3 --help` works immediately after `make install-cli`; it does not require Ansible, Docker, or any service to be reachable.

### `make install-cli`

```bash
pipx install --editable . --force  # installs lv3 CLI from pyproject.toml
# or: ln -sf $(pwd)/scripts/lv3_cli.py /usr/local/bin/lv3 && chmod +x
```

### Shell completion

```bash
lv3 --install-completion bash   # writes to ~/.bashrc
lv3 --install-completion zsh    # writes to ~/.zshrc
```

### Output format example

```
$ lv3 deploy grafana --env staging

🎯  lv3 deploy grafana --env staging
    Route:   build server (build-lv3) → Proxmox staging VM
    Command: ansible-playbook site.yml -l docker_runtime_staging --tags grafana

    Syncing repo to build-lv3...                  ✓  1.2s
    Running validation gate...                    ✓  8.4s
    Applying playbook (staging)...                ✓  94s
    Health check: https://grafana.staging.lv3.org ✓  2.1s

    Receipt: receipts/live-applies/2026-03-22-grafana-staging.json
    Total:   1m 46s
```

### `lv3 status` — the dashboard in a terminal

```
$ lv3 status

PLATFORM STATUS  (lv3.org)                          2026-03-22 09:41 UTC
───────────────────────────────────────────────────────────────────────
SERVICE             VM                    URL                     HEALTH
grafana             monitoring-lv3        grafana.lv3.org         ✓ 200
prometheus          monitoring-lv3        —                       ✓ live
openbao             docker-runtime-lv3    —                       ✓ live
windmill            docker-runtime-lv3    windmill.lv3.org        ✓ 200
keycloak            docker-runtime-lv3    auth.lv3.org            ✓ 200
...

BUILD SERVER        build-lv3             up  • cache warm  • 4 cpus free
STAGING             (no active fixtures)
LAST DEPLOY         grafana  2026-03-21 18:05  (23h ago)
```

## Consequences

**Positive**
- New operators can be productive in minutes: `lv3 --help` describes everything; `lv3 open ops` shows the ops portal
- `lv3 lint`, `lv3 validate`, `lv3 deploy` replace ~20 `make` targets with memorable verb-noun commands
- Routing transparency eliminates "wait, does this run on my laptop?" confusion
- Shell completion makes the CLI pleasant to use; the 30+ commands become browsable
- `--dry-run` and `--explain` on every command lower the fear barrier for new operators

**Negative / Trade-offs**
- The CLI is a thin wrapper; it does not add new capabilities, only a consistent surface over existing ones
- Must be kept in sync with the underlying `make` targets and scripts; a `make` target rename requires a CLI update
- Python's `click` library adds ~200 ms startup overhead vs a compiled binary; acceptable for interactive use

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
