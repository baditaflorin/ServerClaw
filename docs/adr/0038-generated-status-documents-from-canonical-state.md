# ADR 0038: Generated Status Documents From Canonical State

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.41.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The repository is intentionally documentation-heavy, but key status facts are still repeated across:

- `README.md`
- `versions/stack.yaml`
- changelog release notes
- runbooks
- ADR implementation notes

Some repetition is useful, but some of it is pure copy-maintenance.

That creates DRY and consistency risks:

- service counts, versions, URLs, and feature summaries can drift
- updating repo truth after a merge requires touching several prose surfaces by hand
- assistants spend time retyping facts that already exist in machine-readable form

## Decision

We will generate selected status-facing documentation fragments from canonical repository state.

The generated surface should prioritize:

1. README status tables or inventories.
2. Published service and VM summaries.
3. Repo and platform version summaries.
4. Repeated workflow or document indexes where the source already exists elsewhere.
5. Explicit markers that distinguish generated fragments from hand-written narrative text.

## Consequences

- Repeated platform facts stop being maintained in several places by hand.
- Assistants can update canonical sources and regenerate docs instead of editing narrative copies.
- Documentation reviews become simpler because some sections become deterministic outputs.
- The implementation must preserve readable hand-authored narrative and avoid turning the whole README into generated text.

## Implementation Notes

- [scripts/generate_status_docs.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py) now renders selected generated blocks in [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md) from canonical repository state.
- The first generated README surface covers platform status, version summary, document indexes, and merged-workstream summary blocks marked with explicit begin and end comments.
- Canonical inputs currently include [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml), [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml), [workstreams.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml), and the document trees under [docs/runbooks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks), [docs/adr](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr), and [docs/workstreams](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams).
- [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile) now exposes `make generate-status-docs` and `make validate-generated-docs`, and [scripts/validate_repo.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repo.sh) includes generated-doc verification in the standard validation contract.
- Operator usage is documented in [docs/runbooks/generate-status-documents.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/generate-status-documents.md).
