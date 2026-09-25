# WS-0500: Builder private 0mcp transport

## Status

`in_progress` — implementation only. No Builder, VM180, cache, or broker runtime has changed.

## Decision

`fleet-runner`'s private 0mcp transport is privileged Builder topology, not a service setting. A closed role may apply only to `0docker_builder`; it installs the exact root-only transport JSON, a pinned known-hosts file for the 0mcp bastion and VM180, and system SSH configuration that resolves that file while strict checking remains enabled.

## Scope

- Fixed Builder-only transport role, playbook, and root wrapper.
- Pinned host-key material verified against the existing bastion/VM180 pins.
- Static tests for target isolation, exact topology, modes, and strict SSH handling.

## Exclusions

- No SSH private key, GitHub token, certificate, image digest, runtime secret, or live convergence.
- No fallback to 0docker and no host-key bypass.

## Verification

- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_fleet_runner_private_0mcp_transport_role.py`
- Ansible syntax and lint validation.
- Fresh `origin/main` rebase and normal Woodpecker PR validation before merge.

## Merge criteria

1. The playbook can target only `0docker_builder`.
2. The transport and known-host mapping remain exact, root managed, and fail closed.
3. The runner's `ssh -G` preflight resolves the pinned file with strict checking.
4. No credential or deployment operation is included.
