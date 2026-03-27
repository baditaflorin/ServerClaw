# Role Template

Use this directory as the canonical starting point for new repo-managed roles.

Minimum expectations for a new role:

- declare interface variables in `meta/argument_specs.yml`
- document role purpose and key variables in `README.md`
- keep defaults in `defaults/main.yml`
- validate required inputs early in `tasks/main.yml`

Copy this directory to the new role name and replace the example placeholders before wiring the role into a playbook.

ADR 0078 service scaffolds keep the runtime-role templates under `_template/service_scaffold/`. Update those scaffold assets alongside the generic template when the service onboarding contract changes.
