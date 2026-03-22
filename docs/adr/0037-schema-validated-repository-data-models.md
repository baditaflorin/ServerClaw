# ADR 0037: Schema-Validated Repository Data Models

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
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
