# Cross-Workstream Interface Contracts

## Purpose

ADR 0175 makes shared producer-consumer boundaries explicit so parallel workstreams can change safely without relying on hidden chat context.

## Canonical Sources

- contract definitions: [config/contracts](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/contracts)
- validator module: [platform/interface_contracts.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/platform/interface_contracts.py)
- CLI wrapper: [scripts/interface_contracts.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/interface_contracts.py)
- workstream registry source: [workstreams/policy.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/workstreams/policy.yaml), [workstreams/active](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/workstreams/active), and [workstreams/archive](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/workstreams/archive)
- workstream registry compatibility artifact: [workstreams.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/workstreams.yaml)

## Current Contract Set

- `workstream-registry-v1`
  validates the generated `workstreams.yaml` compatibility shape, required fields, unique ids, and doc links consumed by release, drift, and status tooling
- `converge-workflow-live-apply-v1`
  validates the live-apply handoff between `Makefile`, workflow contracts, command contracts, and owner runbooks for `converge-*` workflows

## Validate The Repo Contracts

Run the repo-side validation directly:

```bash
uvx --from pyyaml python scripts/interface_contracts.py --validate
```

Or through the standard Make target:

```bash
make validate-interface-contracts
```

## Inspect One Contract

List the current contracts:

```bash
make interface-contracts
```

Show one contract with the resolved metadata:

```bash
make interface-contract-info CONTRACT=workstream-registry-v1
```

For shard-source edits, also verify the compatibility assembly is current:

```bash
python3 scripts/workstream_registry.py --check
```

## Live Apply Guard

The generic live-apply entrypoints now validate interface contracts before the playbook starts:

- `make live-apply-service service=<service-id> env=production`
- `make live-apply-group group=<group-id> env=production`
- `make live-apply-site env=production`

The guard checks both the contract registry and the referenced playbook surface for the requested apply target.

## Adding A New Shared Contract

1. add a YAML contract file under `config/contracts/`
2. point it at real producer and consumer paths
3. add or reuse a validator function in `platform/interface_contracts.py`
4. add at least one focused test in `tests/test_interface_contracts.py`
5. run `python3 scripts/interface_contracts.py --validate`
