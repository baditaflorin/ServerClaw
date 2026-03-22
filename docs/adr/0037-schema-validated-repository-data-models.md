# ADR 0037: Schema-Validated Repository Data Models

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.40.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

Recent ADRs introduced stronger canonical data sources:

- service topology catalog
- controller-local secret manifest
- shared version and observed-state files

That improves DRY structure, but those models are still validated mostly by convention.

Current risks include:

- accidental field drift between producers and consumers
- misspelled ids that fail only during later execution
- unclear required-versus-optional fields in growing data files
- harder review because shape rules are implicit rather than enforced

## Decision

We will define explicit schemas for the repository's canonical machine-readable data models and validate them in the standard repo gate.

The first schema set should cover:

1. `versions/stack.yaml`
2. the service-topology catalog
3. the controller-local secret manifest
4. any future workflow catalog introduced for execution metadata
5. stable generated JSON artifacts committed to the repo

## Consequences

- Structural errors fail during review instead of during convergence.
- Canonical data models become easier to extend without silent breakage.
- Agents can rely on stronger guarantees when consuming repo data programmatically.
- The first implementation should use a small, readable schema toolchain instead of a heavy framework.

## Implementation Notes

- [scripts/validate_repository_data_models.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repository_data_models.py) now validates the canonical repository data models with a lightweight Python contract instead of adding a heavy external schema framework.
- [scripts/validate_repo.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repo.sh) and [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile) now expose repository data-model validation as a standard stage behind `make validate`.
- The first enforced schema set covers [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml), [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml), [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json), [config/controller-local-secrets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/controller-local-secrets.json), [config/uptime-kuma/monitors.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/uptime-kuma/monitors.json), and the receipt set under [receipts/live-applies](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/live-applies).
- The validator cross-checks `versions/stack.yaml` against canonical host vars so managed guest ids, names, and IPs are verified from one source instead of drifting as duplicated literals.
