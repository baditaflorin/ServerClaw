# ADR 0031: Repository Validation Pipeline For Automation Changes

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
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

