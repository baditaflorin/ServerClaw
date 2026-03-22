# ADR 0062: Ansible Role Composability And DRY Defaults

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The repository now has more than 50 Ansible roles. As the role count has grown, several friction patterns have emerged:

- common variables (package lists, user names, paths, timeouts) are re-declared inside individual roles rather than inherited from a shared layer
- task blocks that perform the same operation (enable and start a systemd unit, assert a file exists, wait for a port) are copy-pasted across roles instead of extracted into shared task files
- role defaults are not validated at entry, so a missing variable produces a confusing mid-task failure rather than a clear preflight error
- adding a new service requires finding and copying boilerplate from whichever role was written most recently

This is a DRY and modularity problem. It slows onboarding, makes audits harder, and increases the chance that a change in one role is not reflected in its copies elsewhere.

## Decision

We will refactor the role layer to enforce composability and eliminate duplication.

Concrete actions:

1. extract a shared task library under `roles/common/tasks/` with named include-able task files for recurring operations:
   - `systemd_unit.yml` — enable, start, and optionally verify a unit
   - `assert_vars.yml` — assert a list of required variables are defined and non-empty
   - `wait_port.yml` — wait for a TCP port with a consistent timeout and retry count
   - `directory_tree.yml` — create a list of directories with consistent owner/mode defaults
2. move cross-cutting variable defaults to `inventory/group_vars/all.yml` or to `roles/common/defaults/main.yml` so individual roles inherit them instead of redeclaring
3. add a `meta/argument_specs.yml` to every new role that declares required and optional variables with types and descriptions — this enables `ansible-lint` to catch missing vars before a play runs
4. establish a role template under `roles/_template/` that new roles copy as a starting point, including the argument spec, a minimal `README.md`, and `defaults/main.yml` with commented-out examples
5. add a lint rule to the existing `make validate` gate that checks every role for the presence of `meta/argument_specs.yml`

## Consequences

- New roles can be written faster and consistently because the boilerplate and common tasks already exist.
- Auditing for a specific behaviour (e.g. how we enable systemd units) requires reading one file instead of scanning all roles.
- The shared task library introduces a dependency that every role must keep in sync with — changes to shared tasks must be tested across all consumers before merging.
- The argument spec requirement will initially generate lint failures for existing roles; these must be resolved before the gate is enforced.

## Boundaries

- Role refactoring does not change idempotency expectations; existing playbooks must pass unchanged after refactoring.
- The shared task library is for task patterns only, not for shared handler definitions; handlers stay inside their owning roles.
- The argument spec linting gate applies to new roles on merge; a follow-up workstream can backfill existing roles.
