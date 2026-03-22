# Validate Repository Automation Runbook

## Purpose

This runbook defines the standard repository validation gate for infrastructure changes.

## Primary Command

Run the full validation pipeline from the repository root:

```bash
make validate
```

This is the required minimum gate before merging automation changes to `main`.

## What The Pipeline Checks

- all managed playbooks pass Ansible syntax check
- generated platform vars are current with canonical stack and host inputs
- repository YAML files pass `yamllint`
- new or changed roles include `meta/argument_specs.yml`
- playbooks and roles pass the repo-managed `ansible-lint` policy
- shell scripts pass `shellcheck`
- repo-managed JSON artifacts pass `jq empty`
- service-owning roles ship and import explicit `tasks/verify.yml` contracts
- canonical repository data models pass schema validation
- generated status documents are current for their canonical inputs
- the workflow catalog, command catalog, control-plane lane catalog, and controller-local secret manifest cross-reference cleanly
- the API publication catalog classifies every governed API and webhook surface
- structured live-apply receipts reference valid workflows, files, and git commits

## Tooling Model

- validation uses `uvx` to run `ansible-core`, `ansible-lint`, and `yamllint`
- validation uses `uvx --from pyyaml python ...` for the repository data-model validator
- required Ansible collections are installed from [collections/requirements.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/requirements.yml)
- validation collections are cached under `.ansible/validation/collections`
- lint-oriented stages operate on tracked repository files so unrelated local work-in-progress does not fail the repo gate
- CI runs the same contract through `make validate`

## Optional Stage Commands

The same pipeline can be run in parts:

```bash
make validate-ansible-syntax
make validate-generated-vars
make validate-yaml
make validate-role-argument-specs
make validate-ansible-lint
make validate-shell
make validate-json
make validate-data-models
make validate-health-probes
make validate-generated-docs
```

`make validate-role-argument-specs` enforces the ADR 0062 contract for role interfaces. It checks role directories that are new or changed relative to `origin/main`, plus any staged, unstaged, or untracked role changes in the current worktree, and fails if a touched role is missing `meta/argument_specs.yml`.

`make validate-data-models` validates the canonical machine-readable repository state, including:

- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)
- [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml)
- [inventory/group_vars/platform.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/group_vars/platform.yml)
- [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json)
- [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/command-catalog.json)
- [config/control-plane-lanes.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/control-plane-lanes.json)
- [config/api-publication.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/api-publication.json)
- [config/controller-local-secrets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/controller-local-secrets.json)
- [config/health-probe-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/health-probe-catalog.json)
- [config/uptime-kuma/monitors.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/uptime-kuma/monitors.json)
- [receipts/live-applies](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/live-applies)

## Troubleshooting

- if validation fails during collection bootstrap, rerun after confirming network access to Ansible Galaxy and package indexes
- if validation fails on generated vars, regenerate [inventory/group_vars/platform.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/group_vars/platform.yml) from the canonical inputs instead of hand-editing the file
- if CI fails but local validation passes, rerun `make validate` from a clean working tree to catch unstaged or ignored-file drift
- if a new file type needs validation, extend [scripts/validate_repo.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repo.sh) and keep `make validate` as the single top-level entry point
