# Workstream ADR 0090: Unified Platform CLI (`lv3`)

- ADR: [ADR 0090](../adr/0090-unified-platform-cli.md)
- Title: Single `lv3` CLI that routes deploy, lint, validate, status, vm, secret, and fixture commands to the right execution target
- Status: merged
- Branch: `codex/adr-0090-platform-cli`
- Worktree: `../proxmox_florin_server-platform-cli`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0082-remote-build-gateway`
- Conflicts With: none
- Shared Surfaces: `scripts/`, `Makefile`, `pyproject.toml`, `config/`

## Scope

- write `scripts/lv3_cli.py` — Python CLI with all 14 command groups documented in the ADR
- write `pyproject.toml` (or update if it exists) with `[project.scripts] lv3 = "scripts.lv3_cli:main"` entry point
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
- implement `lv3 scaffold <name>` wrapping `make scaffold-service NAME=<name>`
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
- `lv3 deploy grafana --dry-run` prints the routed `make remote-exec` command without executing it
- `lv3 open grafana` resolves the catalog URL in the default browser
- shell completion tested: `lv3 dep<TAB>` completes to `lv3 deploy`
- targeted regression coverage: `uv run --with pytest pytest -q tests/test_lv3_cli.py`

## Merge Criteria

- all 14 command groups implemented and pass smoke tests
- `lv3 status` output format matches the layout documented in the ADR
- `docs/runbooks/platform-cli.md` complete with installation, usage examples, and troubleshooting
- commands whose dependent ADR surfaces are still absent fail explicitly with actionable errors instead of inventing ad hoc behavior

## Notes For The Next Assistant

- The shipped CLI is stdlib-only rather than `click`-based so it remains directly runnable as `python3 scripts/lv3_cli.py ...` without extra dependency bootstrapping.
- VM lifecycle, fixtures, and scaffolding now have CLI routes, but the underlying ADR 0085 / 0088 / 0078 repo surfaces are still separate dependencies; keep that explicit if extending those commands.
