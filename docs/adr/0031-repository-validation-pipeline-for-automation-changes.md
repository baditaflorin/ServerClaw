# ADR 0031: Repository Validation Pipeline For Automation Changes

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.32.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The repository already uses syntax checks and targeted playbook commands, but validation is still fragmented.

That leaves several codebase gaps:

- different workstreams may run different checks before merge
- shell scripts, YAML, and dashboard templates do not share one predictable validation entry point
- review quality depends too much on chat memory instead of a repeatable gate
- integration to `main` can succeed even when maintainability checks were never run together

The codebase needs one consistent validation contract for infrastructure changes.

## Decision

We will define one repository validation pipeline and make it the standard integration gate.

The pipeline will include:

1. A single top-level command such as `make validate`.
2. Static checks for Ansible syntax and YAML structure.
3. Linting for Ansible, shell scripts, and repository-managed JSON or generated artifacts where applicable.
4. A documented minimum validation set that every workstream must pass before merge to `main`.
5. A CI path that runs the same validation contract as the local developer entry point instead of a separate hidden rule set.

## Consequences

- Merge readiness becomes easier to reason about because the expected gate is uniform.
- Repo quality stops depending on which assistant or operator touched a branch.
- Validation failures move earlier in the workflow.
- Introducing the pipeline will require some cleanup of existing files to make them lintable on purpose instead of by exception.

## Implementation Notes

- `make validate` is now the top-level repository gate and fans out into syntax, YAML, Ansible lint, shell, and JSON validation stages.
- Validation is implemented in [scripts/validate_repo.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repo.sh) and mirrored in CI through [.github/workflows/validate.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.github/workflows/validate.yml).
- The validation path installs required Ansible collections from [collections/requirements.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/requirements.yml) and uses repo-managed lint policies from [.ansible-lint](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.ansible-lint) and [.yamllint](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.yamllint).
- The minimum merge gate is documented in the new validation runbook and referenced from the release and workstream guidance.
