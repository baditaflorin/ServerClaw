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
- repository YAML files pass `yamllint`
- playbooks and roles pass the repo-managed `ansible-lint` policy
- shell scripts pass `shellcheck`
- repo-managed JSON artifacts pass `jq empty`
- the workflow catalog and controller-local secret manifest cross-reference cleanly
- structured live-apply receipts reference valid workflows, files, and git commits

## Tooling Model

- validation uses `uvx` to run `ansible-core`, `ansible-lint`, and `yamllint`
- required Ansible collections are installed from [collections/requirements.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/requirements.yml)
- validation collections are cached under `.ansible/validation/collections`
- CI runs the same contract through `make validate`

## Optional Stage Commands

The same pipeline can be run in parts:

```bash
make validate-ansible-syntax
make validate-yaml
make validate-ansible-lint
make validate-shell
make validate-json
```

## Troubleshooting

- if validation fails during collection bootstrap, rerun after confirming network access to Ansible Galaxy and package indexes
- if CI fails but local validation passes, rerun `make validate` from a clean working tree to catch unstaged or ignored-file drift
- if a new file type needs validation, extend [scripts/validate_repo.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repo.sh) and keep `make validate` as the single top-level entry point
