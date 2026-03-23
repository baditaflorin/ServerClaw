# Platform Facts Library

## Purpose

This runbook documents the generated platform facts layer introduced by ADR 0063.

The goal is to keep host and service topology facts in one committed, agent-readable file instead of repeating computed values across role defaults and shared vars.

## Canonical Inputs

The generated facts library is built from:

- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)
- [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml)

The committed output is:

- [inventory/group_vars/platform.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/group_vars/platform.yml)

Do not hand-edit `platform.yml`.

## Primary Commands

Regenerate the committed file:

```bash
make generate-platform-vars
```

Verify that the committed file is current:

```bash
make validate-generated-vars
```

Inspect resolved inventory facts for one host without running a playbook:

```bash
make show-platform-facts HOST=proxmox_florin
make show-platform-facts HOST=docker-runtime-lv3
```

## What Lives In The Generated File

- resolved host management and network facts
- guest inventory indexed by name and role
- resolved service topology with private IPs, DNS targets, and public or controller URLs
- resolved DNS record lists for public and tailnet publication
- shared computed URLs and ports that would otherwise be repeated across roles

## Validation Contract

`make validate` now includes a generated-vars stage that:

1. rebuilds the platform facts model from canonical inputs
2. compares the result to the committed `platform.yml`
3. fails if the committed file is stale

The repository data-model validator also checks that the generated file matches the current canonical inputs.

## Change Rules

- update `versions/stack.yaml` or canonical host vars first
- regenerate `inventory/group_vars/platform.yml`
- remove duplicated computed facts from role defaults or shared vars when the generated layer becomes the clearer source
- rerun `make validate` before merging
