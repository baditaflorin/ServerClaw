# Workstream ADR 0205: Capability Contracts Before Product Selection

- ADR: [ADR 0205](../adr/0205-capability-contracts-before-product-selection.md)
- Title: Contract-first capability catalog with manifest and ops portal visibility
- Status: ready
- Implemented In Repo Version: N/A (pending merge to main)
- Implemented In Platform Version: N/A
- Implemented On: N/A
- Branch: `codex/ws-0205-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0205-live-apply`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0093-interactive-ops-portal`, `adr-0132-self-describing-platform-manifest`, `adr-0204-architecture-governance`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0205-capability-contracts-before-product-selection.md`, `config/capability-contract-catalog.json`, `scripts/capability_contracts.py`, `scripts/platform_manifest.py`, `scripts/ops_portal/app.py`, `workstreams.yaml`

## Scope

- define a machine-readable contract catalog for critical shared platform capabilities before product selection
- validate contract structure and cross references against service, ADR, and runbook surfaces
- surface the catalog in the platform manifest and the interactive ops portal
- update operator runbooks so new critical product choices follow the contract-first path
- perform a live replay of `ops_portal` so the new catalog is visible on a real platform surface

## Non-Goals

- implementing ADR 0212 replaceability scorecards and exit plans in full
- forcing every existing service into a new completeness gate item
- updating protected integration truth files on the workstream branch

## Expected Repo Surfaces

- `config/capability-contract-catalog.json`
- `docs/schema/capability-contract-catalog.schema.json`
- `scripts/capability_contracts.py`
- `tests/test_capability_contracts.py`
- `scripts/platform_manifest.py`
- `docs/schema/platform-manifest.schema.json`
- `scripts/ops_portal/app.py`
- `scripts/ops_portal/templates/partials/overview.html`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`
- `docs/runbooks/capability-contract-catalog.md`
- `docs/runbooks/add-a-new-service.md`
- `docs/runbooks/scaffold-new-service.md`
- `docs/runbooks/platform-manifest.md`
- `docs/workstreams/adr-0205-capability-contracts-before-product-selection.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `http://10.10.10.20:8092` renders the new `Capability Contracts` panel in the interactive ops portal after converge
- `https://ops.lv3.org` exposes the same contract-first summary behind the existing auth gate after the `ops_portal` replay

## Verification

- `uv run --with pyyaml --with jsonschema python scripts/capability_contracts.py --validate`
- `uv run --with pytest --with jsonschema --with-requirements requirements/ops-portal.txt python -m pytest tests/test_capability_contracts.py tests/test_platform_manifest.py tests/test_interactive_ops_portal.py -q`
- `./scripts/validate_repo.sh data-models generated-portals agent-standards`
- `make generate-platform-manifest`
- `make live-apply-service service=ops_portal env=production`

## Merge Criteria

- every committed capability contract captures outcomes, inputs, outputs, security, audit, observability, portability, migration, and failure handling
- the manifest and interactive ops portal render contract-first capability visibility without breaking existing operator surfaces
- the workstream records live-apply evidence and clearly notes the protected integration files that still wait for merge-to-main

## Notes For The Next Assistant

- protected integration files remain intentionally deferred on this branch until a merge-to-main step: `VERSION`, release sections in `changelog.md`, `README.md`, and `versions/stack.yaml`
- if the live apply succeeds but a later main merge is done by another agent, update ADR 0205 with the final repo version and refresh `docs/adr/.index.yaml` again at the end of that merge step
