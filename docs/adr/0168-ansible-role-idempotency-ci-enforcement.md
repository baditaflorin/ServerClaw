# ADR 0168: Ansible Role Idempotency CI Enforcement

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.146.0
- Implemented In Platform Version: n/a
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

Ansible is the platform convergence engine. Re-running a role against an already-converged target must be safe and predictable, otherwise the observation loop, drift tooling, and operator re-apply workflows become noisy or dangerous.

Before this ADR:

- the repository had only one delegated Molecule scenario, and it depended on the Proxmox ephemeral fixture path rather than the default GitHub validation job
- most roles had no repo-tracked idempotency coverage state at all
- CI had no explicit enforcement boundary that prevented a new role from being added without any idempotency plan

That left the repository with two problems:

1. It was easy to overstate idempotency coverage because the missing-role set was implicit.
2. The existing fixture-backed testing path was valuable, but not the default CI baseline because it was not runnable on GitHub-hosted runners.

The repository needed an explicit coverage contract that could run in normal CI today while keeping the migration inventory visible for the heavier roles.

## Decision

We will enforce Ansible role idempotency through a **repo-managed coverage policy** and a **CI validation gate**.

### Coverage policy

Every role in `collections/ansible_collections/lv3/platform/roles/` must appear in `config/ansible-role-idempotency.yml` and declare exactly one policy:

- `enforced`: a repo-managed two-pass scenario runs in CI and the second pass must report zero changes
- `tracked`: the role remains on the migration inventory until a CI-safe scenario exists
- `exempt`: the entry is not a standalone runnable role, such as a scaffold or shared include library

CI fails if:

- a role on disk is missing from the policy file
- the policy file names a role that no longer exists
- an `enforced` role is missing its scenario playbook
- an `enforced` role reports changed tasks on the second run

### Initial enforced baseline

The first CI-safe enforced scenarios are localhost playbooks under `tests/idempotency/`:

- `preflight`
- `secret_fact`
- `wait_for_healthy`

These roles are deterministic on a GitHub-hosted runner and prove the two-pass gate end to end without depending on the Proxmox delegated fixture path.

### Runtime model

The validation entrypoint is `scripts/ansible_role_idempotency.py`, which:

1. validates policy completeness against the live role tree
2. starts deterministic local HTTP fixtures when a scenario declares one
3. runs the scenario playbook twice with `ANSIBLE_STDOUT_CALLBACK=json`
4. parses the second run and fails if any task still reports `changed`

The stage is wired into:

- `make validate-ansible-idempotency`
- `scripts/validate_repo.sh`
- `.github/workflows/validate.yml`

## Consequences

**Positive**

- the repository now has an explicit idempotency coverage contract for every role instead of an undocumented gap
- CI blocks new role-tree drift immediately because every role must be classified
- helper roles that are safe on default runners now have true two-pass enforcement on every validation run
- infrastructure-heavy roles remain visible in a tracked migration inventory instead of being silently ignored

**Negative / Trade-offs**

- most runtime-heavy roles still need dedicated CI-safe fixtures before they can move from `tracked` to `enforced`
- the delegated Proxmox Molecule path remains useful, but it is not yet the baseline CI mechanism
- operators must keep the coverage manifest current whenever roles are added, removed, or promoted

## Boundaries

- This ADR covers Ansible roles in `collections/ansible_collections/lv3/platform/roles/`.
- It does not claim that every role is already backed by a full local fixture.
- It does not replace fixture-backed validation for roles that require Proxmox, Docker nesting, or other heavier environments.

## Related ADRs

- ADR 0083: Docker-based check runner
- ADR 0087: Repository validation gate
- ADR 0088: Ephemeral infrastructure fixtures
- ADR 0111: End-to-end integration test suite
