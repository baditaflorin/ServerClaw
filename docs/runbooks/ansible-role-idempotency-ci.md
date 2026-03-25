# Ansible Role Idempotency CI

## Purpose

This runbook describes the repo-managed idempotency coverage gate for Ansible roles.

The policy file at [config/ansible-role-idempotency.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/ansible-role-idempotency.yml) is the source of truth for every role under [collections/ansible_collections/lv3/platform/roles/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/ansible_collections/lv3/platform/roles).

## Policy States

- `enforced`: the role has a repo-managed two-pass idempotency scenario and must report zero changes on the second run
- `tracked`: the role is on the migration inventory and must stay explicitly listed until a CI-safe scenario exists
- `exempt`: the entry is intentionally not a standalone runnable role, such as a scaffold or shared include library

The gate fails if:

- a role exists on disk but is missing from the policy file
- a policy entry references a role that no longer exists
- an `enforced` role is missing its scenario playbook
- an `enforced` role reports any changed task on the second run

## Run The Gate

Run the policy validation and the enforced scenarios:

```bash
make validate-ansible-idempotency
```

Equivalent direct invocation:

```bash
uv run --with pyyaml python scripts/ansible_role_idempotency.py
```

If you only need to verify that coverage metadata is complete, skip runtime execution:

```bash
uv run --with pyyaml python scripts/ansible_role_idempotency.py --manifest-only
```

## Promote A Role To Enforced

1. Add a CI-safe playbook under [tests/idempotency/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/tests/idempotency).
2. If the scenario needs a deterministic local HTTP dependency, declare it in `scenario.http_fixture`.
3. Change the role policy in `config/ansible-role-idempotency.yml` from `tracked` to `enforced`.
4. Run `make validate-ansible-idempotency`.
5. Keep the role in `tracked` until the second run is clean on CI, not just locally.

## Notes

- The current baseline enforces helper roles that are safe to execute on GitHub-hosted runners and keeps infrastructure-heavy roles visible in the tracked migration inventory.
- The existing delegated Molecule path for `docker_runtime` remains useful for fixture-backed validation, but it is not yet the CI-safe baseline gate because it depends on the Proxmox ephemeral fixture workflow.
