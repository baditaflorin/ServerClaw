# Generate Status Documents

## Purpose

This runbook defines how the repository regenerates selected README status sections from canonical machine-readable state instead of maintaining repeated copies by hand.

## Primary Commands

Regenerate the managed README fragments:

```bash
make generate-status-docs
```

Verify the generated fragments are current without rewriting files:

```bash
make validate-generated-docs
```

## Generated Surface

The current implementation updates explicit generated blocks in [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/README.md):

- platform status inventory
- document index
- version summary
- merged workstream summary

Each generated block is marked in the README so hand-authored narrative stays separate from deterministic generated content.

## Canonical Inputs

The generator reads from:

- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/versions/stack.yaml)
- [inventory/host_vars/proxmox-host.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/host_vars/proxmox-host.yml)
- [workstreams.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/workstreams.yaml)
- [docs/runbooks](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks)
- [docs/adr](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr)
- [docs/workstreams](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/workstreams)

## Tooling Model

- generation is handled by [scripts/generate_status_docs.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/generate_status_docs.py)
- the script uses the same PyYAML-based execution model as the repository data-model validator
- `make validate` includes `make validate-generated-docs`, so stale generated fragments fail the standard repo gate

## Change Rules

- edit canonical inputs first
- regenerate the README fragments second
- do not hand-edit text inside generated markers
- if a new generated README block is added, update the generator, this runbook, and the validation workflow together
