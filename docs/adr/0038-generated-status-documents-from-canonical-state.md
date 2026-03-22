# ADR 0038: Generated Status Documents From Canonical State

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
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
