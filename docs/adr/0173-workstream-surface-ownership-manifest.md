# ADR 0173: Workstream Surface Ownership Manifest

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.176.1
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-27
- Date: 2026-03-26

## Context

The repository already supports parallel workstreams through `workstreams.yaml`, branch-per-workstream conventions, and explicit protection of integration-only files in `AGENTS.md`. That is a strong start, but it is still too easy for two agents to edit the same operational surface at the same time:

- one workstream updates `inventory/host_vars/proxmox_florin.yml`
- another changes a role default consumed by the same host
- a third edits a shared generated config under `config/`

These conflicts are not always visible from file paths alone. A role, template, host variable, and generated artifact can all belong to the same operational surface even when they live in different directories.

To work safely in parallel, workstreams need a machine-readable declaration of which surfaces they own, which ones they only read, and which ones are shared by contract.

## Decision

We will define a **surface ownership manifest** for every active workstream. The manifest becomes the canonical declaration of what that workstream may mutate.

### Surface classes

Each declared surface uses one of these ownership modes:

- `exclusive`: only one active workstream may mutate the surface
- `shared_contract`: multiple workstreams may touch the surface only through a declared interface contract
- `generated`: the surface is written only by a generator or integration assembler
- `read_only`: the workstream may depend on the surface but may not modify it

### Manifest shape

Each workstream document gains a companion manifest entry:

```yaml
workstream_id: adr-0173-example
owned_surfaces:
  - id: runtime_netbox_role
    paths:
      - collections/ansible_collections/lv3/platform/roles/netbox_runtime/**
    mode: exclusive

  - id: service_catalog_contract
    paths:
      - config/service-capability-catalog.json
    mode: shared_contract
    contract: service-capability-catalog-v1

  - id: stack_summary
    paths:
      - README.md
      - VERSION
      - changelog.md
      - versions/stack.yaml
    mode: generated
```

### Enforcement

Validation will reject a workstream branch when it:

1. edits a path outside its declared owned surfaces
2. edits a `generated` surface directly
3. claims `exclusive` ownership of a surface already owned by another active workstream

The repository implementation now enforces this with:

- `ownership_manifest` entries for active workstreams in `workstreams.yaml`
- `scripts/workstream_surface_ownership.py` for registry and branch diff validation
- `scripts/validate_repository_data_models.py` integration for schema checks
- `scripts/validate_repo.sh workstream-surfaces` for branch-local enforcement

### Ownership transfer

When a workstream must hand off a surface, the transfer happens by updating the manifest and the relevant workstream doc in the same change. Ownership transfer is explicit, reviewable, and does not rely on chat history.

## Consequences

**Positive**

- Parallel work becomes safer because each agent has a declared write boundary.
- Reviewers can reason about conflicts from surface IDs instead of diff spelunking.
- Workstream handoff becomes durable and visible in git.

**Negative / Trade-offs**

- Surface manifests add maintenance overhead.
- Some surfaces will need careful decomposition before they can be owned cleanly.

## Boundaries

- This ADR governs repository and automation surfaces, not runtime resource locking. Runtime execution still uses ADRs 0153-0162.
- Declaring ownership does not remove the need for tests and integration review.

## Related ADRs

- ADR 0075: Service capability catalog
- ADR 0153: Distributed resource lock registry
- ADR 0154: VM-scoped parallel execution lanes
- ADR 0156: Agent session workspace isolation
- ADR 0174: Integration-only canonical truth assembly
