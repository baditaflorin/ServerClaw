# Bounded Command Execution

## Purpose

This runbook defines how governed commands move from a validated command
contract into a bounded transient `systemd-run` unit on the server-resident
runtime.

## Canonical Sources

- ADR: [docs/adr/0227-bounded-command-execution-via-systemd-run-and-approved-wrappers.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0227-bounded-command-execution-via-systemd-run-and-approved-wrappers.md)
- command catalog: [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/command-catalog.json)
- controller launcher: [scripts/governed_command.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/governed_command.py)
- runtime helper: [scripts/governed_command_runtime.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/governed_command_runtime.py)
- agent tool surface: [scripts/agent_tool_registry.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/agent_tool_registry.py)
- live-apply evidence model: [docs/runbooks/live-apply-receipts-and-verification-evidence.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/live-apply-receipts-and-verification-evidence.md)

## Execution Model

Each governed command now declares:

- an execution profile from the command catalog
- a per-command timeout
- the effective runtime user
- the runtime working directory
- any required runtime environment overrides
- the `systemd` kill mode
- receipt and log destinations

The controller-side launcher stages any required controller-local file secrets
into repo-local runtime paths, forwards approved environment variables and
operator parameters, then submits the payload to the runtime helper over the
existing SSH path.

The runtime helper converts that payload into a transient `systemd-run` unit so
the command survives client disconnects and leaves durable logs and receipts.
Execution profiles can also pin guest-local service URLs when the runtime
wrapper must call a service from inside the worker VM. ADR 0227 now uses that
contract for `network-impairment-matrix` so the governed replay targets
`http://127.0.0.1:8000` on `docker-runtime-lv3` instead of a controller-side
proxy address.

## Primary Commands

Dry-run one governed command and inspect the bounded execution metadata without
executing it:

```bash
python3 scripts/governed_command.py \
  --command network-impairment-matrix \
  --requester-class human_operator \
  --approver-classes human_operator \
  --preflight-passed \
  --validation-passed \
  --receipt-planned \
  --param NETWORK_IMPAIRMENT_MATRIX_ARGS='target_class=staging --approve-risk' \
  --dry-run
```

Execute the same governed command through the transient unit wrapper:

```bash
python3 scripts/governed_command.py \
  --command network-impairment-matrix \
  --requester-class human_operator \
  --approver-classes human_operator \
  --preflight-passed \
  --validation-passed \
  --receipt-planned \
  --param NETWORK_IMPAIRMENT_MATRIX_ARGS='target_class=staging --approve-risk'
```

The governed `network-impairment-matrix` wrapper now resolves to:

```bash
uv run --with pyyaml --with nats-py python scripts/lv3_cli.py run \
  network-impairment-matrix --args target_class=staging --approve-risk
```

Validate the repo-side contracts before a live apply:

```bash
python3 scripts/command_catalog.py --validate
python3 scripts/agent_tool_registry.py --validate
./scripts/validate_repo.sh agent-standards
```

## Runtime Outputs

The command response returns:

- `runtime_host`
- `unit_name`
- `stdout_log`
- `stderr_log`
- `receipt_path`

On the runtime host, these paths live under the repo checkout:

- stdout and stderr logs: `.local/governed-command/logs/`
- bounded execution receipts: `.local/governed-command/receipts/`
- execution-lane state registry: `.local/state/execution-lanes/registry.json`
  and `.local/state/execution-lanes/registry.lock`

The runtime helper also maintains the compatibility symlink for
`/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server` when the worker
checkout actually lives at `/srv/proxmox_florin_server`.

The worker converge now also enforces the execution-lane registry directory and
files as mutable runtime surfaces so `ops`-scoped governed commands can acquire
their coordination lock without root-owned write failures.

## Live Apply Repair Note

The 2026-03-28 ADR 0227 live apply exposed a pre-existing permissions edge on
`docker-runtime-lv3`: the execution-lane registry files already existed as
root-owned `0644` files before the new mutable-file contract was converged.

After the role change landed, a one-time repair was required on the live guest:

```bash
sudo chmod 0666 \
  /srv/proxmox_florin_server/.local/state/execution-lanes/registry.json \
  /srv/proxmox_florin_server/.local/state/execution-lanes/registry.lock
```

That chmod is not the long-term operating model. The repository contract now
declares those files as worker-mutable so future converges recreate or preserve
the correct permissions automatically.

## Operating Rule

Before executing a mutating governed command:

1. validate the command catalog and agent tool registry
2. confirm the approval decision, operator parameters, and receipt plan
3. ensure any controller-local file secrets required by the command are present
   either on the controller or already mirrored into the runtime checkout
4. execute the governed command through [scripts/governed_command.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/governed_command.py) or the `run-governed-command` tool rather than calling the Make target directly from a controller shell
5. capture the transient unit name plus the stdout, stderr, and receipt paths in the live-apply evidence
