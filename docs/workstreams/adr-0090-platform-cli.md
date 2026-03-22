# Workstream ADR 0090: Unified Platform CLI (`lv3`)

- ADR: [ADR 0090](../adr/0090-unified-platform-cli.md)
- Title: Single `lv3` CLI that routes deploy, lint, validate, status, vm, secret, and fixture commands to the right execution target
- Status: ready
- Branch: `codex/adr-0090-platform-cli`
- Worktree: `../proxmox_florin_server-platform-cli`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0082-remote-build-gateway`
- Conflicts With: none
- Shared Surfaces: `scripts/`, `Makefile`, `pyproject.toml`, `config/`

## Scope

- write `scripts/lv3_cli.py` — `click`-based CLI with all 14 command groups documented in the ADR
- write `pyproject.toml` (or update if it exists) with `[project.scripts] lv3 = "scripts.lv3_cli:cli"` entry point
- add `make install-cli` target (pipx editable install)
- add `make update-cli` target (re-installs after changes)
- implement `lv3 status` reading `config/service-capability-catalog.json` and probing health endpoints concurrently
- implement `lv3 deploy <service>` routing to `make remote-exec` with the correct playbook and tags
- implement `lv3 lint`, `lv3 validate` routing to `make remote-lint`, `make remote-validate`
- implement `lv3 vm <create|destroy|resize|list>` routing to `make remote-tofu-apply/plan`
- implement `lv3 fixture <up|down>` routing to `make fixture-up/down`
- implement `lv3 open <service>` opening the service URL in the default browser
- implement `lv3 ssh <vm-name>` resolving VM Tailscale IP from inventory and calling `ssh ops@<ip>`
- implement `lv3 logs <service>` calling Loki API with the service label filter
- implement `lv3 scaffold <name>` wrapping `make scaffold-service SERVICE=<name>`
- implement shell completion for bash and zsh
- write `docs/runbooks/platform-cli.md` with install guide and command reference

## Non-Goals

- a TUI (terminal UI) — plain CLI only for now
- API server mode for the CLI
- Windows support

## Expected Repo Surfaces

- `scripts/lv3_cli.py`
- updated `pyproject.toml`
- updated `Makefile` (`install-cli`, `update-cli`)
- `docs/runbooks/platform-cli.md`
- `docs/adr/0090-unified-platform-cli.md`
- `docs/workstreams/adr-0090-platform-cli.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `lv3 --version` prints `0.1.0` (CLI version tracks separately from repo version)
- `lv3 status` shows a health table with all services from the service catalog
- `lv3 lint` routes to `make remote-lint` and streams output correctly
- `lv3 --install-completion bash` adds completion to `~/.bashrc`

## Verification

- `make install-cli` installs `lv3` in `PATH`; `lv3 --help` shows all command groups
- `lv3 status` returns within 5 s with concurrent health probes for all live services
- `lv3 deploy grafana --dry-run` prints the Ansible command it would run without executing it
- `lv3 open grafana` opens `https://grafana.lv3.org` in the default browser
- shell completion tested: `lv3 dep<TAB>` completes to `lv3 deploy`

## Merge Criteria

- all 14 command groups implemented and pass smoke tests
- `lv3 status` output format matches the layout documented in the ADR
- `docs/runbooks/platform-cli.md` complete with installation, usage examples, and troubleshooting

## Notes For The Next Assistant

- use `click.echo` with ANSI colour codes for the status table; add a `--no-color` flag for CI environments; honour `NO_COLOR` env var
- `lv3 status` health probes should have a 3-second timeout per service; failures should show as `✗ timeout` not crash the command
- the `lv3 logs` command needs a `--since` flag accepting natural language time (`10m`, `2h`, `1d`); convert to Loki `start` timestamp in the command before the Loki API call
- `lv3 deploy` must print the receipt URL at the end; read the last-created file in `receipts/live-applies/` matching the service name and date
