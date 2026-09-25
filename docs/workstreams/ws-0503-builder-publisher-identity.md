# WS-0503: Builder LXC108 fleet-runner publisher identity

## Status

`in_progress` — implementation only; no host has been changed and no image has
been published by this workstream.

## Decision

The dedicated Builder LXC108 is the only allowed fleet-runner image-publishing
surface. It receives a fixed, non-secret local identity contract at
`/etc/fleet-runner/image-publisher.json`. General platform `docker-build`
guests do not receive the file.

The role, collection playbook, and root wrapper all use the exact inventory
hostname `0docker_builder`; the role rejects target, identity, path, version,
or mode overrides before it creates the parent directory. The fixed payload
identity remains `builder-lxc-108`. The parent must be a real `root:root`
`0700` directory and the JSON contract must be a regular
`root:root` `0600` file with the exact fixed payload
`{"version":1,"identity":"builder-lxc-108"}`.

## Scope

- A dedicated, closed Ansible role and controlled converge entrypoint.
- Focused static tests for host isolation, exact payload, parent safety, and
  ownership/mode requirements.
- A runbook describing safe invocation and non-sensitive verification.

## Explicit exclusions

- No live convergence, Docker changes, cache changes, broker changes, registry
  configuration, credentials, tokens, secrets, network addresses, or release
  version changes.
- No general `build_server` role changes: that role manages the platform
  `docker-build` VM, not the dedicated Builder LXC108.

## Verification

- `pytest -q tests/test_fleet_runner_image_publisher_identity_role.py`
- applicable repository IaC syntax and policy validation
- review from a fresh `origin/main` rebase before push

### Current evidence

The focused role test, workstream ownership tests, Ansible syntax check,
Ansible lint, agent-standards check, and workstream-surface check pass on this
branch. `make validate` currently stops at generated-platform-vars validation
before evaluating this workstream: a separate pristine `origin/main` worktree
reproduces the same `inventory/group_vars/platform.yml must match
scripts/generate_platform_vars.py output` failure. This workstream does not
touch that generated artifact and must rebase onto the separately repaired
baseline before it is pushed for CI.

## Merge criteria

1. The contract remains hard-coded to `builder-lxc-108` and cannot target a
   general build host.
2. The write is root-only and exact; neither path traversal nor a symlink
   parent/file is accepted.
3. Tests and required Woodpecker checks are green.
4. The PR is reviewable and merged through the repository PR policy; live
   convergence stays a separately authorized operation.
