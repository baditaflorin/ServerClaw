# Workstream ADR 0204: Architecture Governance Bundle

- ADR: [ADR 0204](../adr/0204-self-correcting-automation-loops.md)
- Title: Ten governance ADRs for self-correction, clean boundaries, DRY policy reuse, and vendor replaceability
- Status: merged
- Implemented In Repo Version: 0.177.23
- Implemented In Platform Version: N/A
- Implemented On: 2026-03-28
- Branch: `codex/adr-0204-architecture-governance`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/adr-0204-architecture-governance`
- Owner: codex
- Depends On: `adr-0030-role-interface-contracts`, `adr-0062-role-composability`, `adr-0175-cross-workstream-interface-contracts`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0204-0213`, `docs/adr/.index.yaml`, `docs/workstreams/adr-0204-architecture-governance.md`, `workstreams.yaml`, `VERSION`, `changelog.md`, `docs/release-notes/`

## Scope

- add ten accepted ADRs that define the target architecture for self-correction,
  contract-first capability choices, clean dependency boundaries, policy reuse,
  and low-lock-in product selection
- record the bundle in the workstream registry and release metadata
- regenerate ADR discovery metadata so future assistants can find the new
  decisions quickly
- refresh integration-generated artifacts that the release gate requires to stay
  current after repo-version and canonical-truth changes

## Non-Goals

- implementing the validators, adapters, or refactors implied by the new ADRs
- claiming any live platform mutation or platform-version change
- rewriting existing code to full clean architecture in one pass

## Expected Repo Surfaces

- `docs/adr/0204-self-correcting-automation-loops.md`
- `docs/adr/0205-capability-contracts-before-product-selection.md`
- `docs/adr/0206-ports-and-adapters-for-external-integrations.md`
- `docs/adr/0207-anti-corruption-layers-at-provider-boundaries.md`
- `docs/adr/0208-dependency-direction-and-composition-roots.md`
- `docs/adr/0209-use-case-services-and-thin-delivery-adapters.md`
- `docs/adr/0210-canonical-domain-models-over-vendor-schemas.md`
- `docs/adr/0211-shared-policy-packs-and-rule-registries.md`
- `docs/adr/0212-replaceability-scorecards-and-vendor-exit-plans.md`
- `docs/adr/0213-architecture-fitness-functions-in-the-validation-gate.md`
- `docs/adr/.index.yaml`
- `config/ansible-role-idempotency.yml`
- `docs/workstreams/adr-0204-architecture-governance.md`
- `workstreams.yaml`
- `VERSION`
- `changelog.md`
- `RELEASE.md`
- `docs/release-notes/0.177.23.md`
- `versions/stack.yaml`
- `README.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`

## Expected Live Surfaces

- none; this is a repo-only governance release

## Ownership Notes

- the workstream owns the new ADR bundle and its release metadata
- no platform canonical state files under `versions/stack.yaml` are touched
- future implementation work should reference these ADRs rather than treating
  the bundle as already enforced in code

## Verification

- Run `uv run --with pyyaml python scripts/generate_adr_index.py --write`
- Run `make generate-platform-manifest`
- Run `./scripts/validate_repo.sh agent-standards`
- Run `make validate`

## Merge Criteria

- all ten ADRs read as one coherent architecture direction rather than ten
  isolated wishes
- the ADR index and platform manifest include the new decision records
- the release metadata reflects a repo-only `main` integration with no platform
  version bump claim

## Outcome

- recorded in repo version `0.177.23`
- the repository now records a clear architecture direction for self-correction,
  contract-first capability boundaries, ports and adapters, anti-corruption
  layers, clean dependency flow, shared policy packs, and vendor exit planning
- no platform version bump was required because this change is governance-only
- the integration step also repaired pre-existing workstream-registry drift for
  ADR 0149 and refreshed canonical mainline truth files required by the release
  gate

## Notes For The Next Assistant

- implement ADR 0213 early if you want these decisions to stay honest; the
  validation gate is the most direct self-correction lever
- when introducing a new product, start with ADR 0205 and ADR 0212 before
  touching runtime code
- if a future feature spans CLI, API, and workflow surfaces, ADR 0209 should be
  the first duplication check
