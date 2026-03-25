# Workstream ADR 0168: Ansible Role Idempotency CI Enforcement

- ADR: [ADR 0168](../adr/0168-ansible-role-idempotency-ci-enforcement.md)
- Title: Repo-managed idempotency coverage policy and CI gate for Ansible roles
- Status: merged
- Implemented In Repo Version: 0.146.0
- Implemented In Platform Version: n/a
- Implemented On: 2026-03-25
- Branch: `codex/adr-0168-idempotency-ci`
- Worktree: `.worktrees/adr-0168-idempotency-ci`
- Owner: codex
- Depends On: `adr-0083-docker-check-runner`, `adr-0087-validation-gate`
- Conflicts With: none
- Shared Surfaces: `config/`, `scripts/`, `.github/workflows/validate.yml`, `tests/idempotency/`, `docs/runbooks/`

## Scope

- add a repo-managed coverage manifest for every Ansible role
- add a validation script that enforces manifest completeness and runs two-pass scenarios for CI-safe roles
- add initial localhost scenarios for helper roles that are safe on GitHub-hosted runners
- wire the new stage into `make validate` and the GitHub validation workflow
- document how roles move from `tracked` to `enforced`
- update ADR 0168 metadata to reflect the implemented repo-side contract

## Non-Goals

- claiming that all infrastructure-heavy roles already have CI-safe local fixtures
- replacing the delegated Proxmox Molecule path for live fixture validation
- changing `platform_version`; this is a repository-only rollout

## Expected Repo Surfaces

- `config/ansible-role-idempotency.yml`
- `scripts/ansible_role_idempotency.py`
- `tests/idempotency/`
- `docs/runbooks/ansible-role-idempotency-ci.md`
- `docs/adr/0168-ansible-role-idempotency-ci-enforcement.md`
- `docs/workstreams/adr-0168-idempotency-ci.md`
- `scripts/validate_repo.sh`
- `Makefile`
- `.github/workflows/validate.yml`

## Expected Live Surfaces

- GitHub Actions `Validate` runs the new idempotency stage through `make validate`
- new roles cannot bypass the policy manifest
- enforced helper-role scenarios must stay idempotent on `main`

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_ansible_role_idempotency.py tests/test_validate_repo_cache.py -q`
- `uv run --with pyyaml python scripts/ansible_role_idempotency.py`
- `make validate`

## Merge Criteria

- every role is explicitly classified in `config/ansible-role-idempotency.yml`
- enforced scenarios pass with zero second-run changes
- `make validate` includes the idempotency stage
- ADR 0168 and the runbook reflect the implemented repo-side policy

## Delivered

- added explicit policy coverage for all 70 current roles
- added a reusable idempotency runner with deterministic HTTP fixtures for localhost scenarios
- promoted `preflight`, `secret_fact`, and `wait_for_healthy` into enforced two-pass checks
- wired the new gate into repository validation and GitHub Actions
- documented the tracked-to-enforced promotion path for future role workstreams
