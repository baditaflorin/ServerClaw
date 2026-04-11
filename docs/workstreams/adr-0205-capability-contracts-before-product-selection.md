# Workstream ADR 0205: Capability Contracts Before Product Selection

- ADR: [ADR 0205](../adr/0205-capability-contracts-before-product-selection.md)
- Title: Contract-first capability catalog with manifest and ops portal visibility
- Status: merged
- Implemented In Repo Version: 0.177.41
- Implemented In Platform Version: 0.130.39
- Implemented On: 2026-03-28
- Branch: `codex/ws-0205-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0205-live-apply`
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
- `https://ops.example.com` exposes the same contract-first summary behind the existing auth gate after the `ops_portal` replay

## Verification

- `uv run --with pyyaml --with jsonschema python scripts/capability_contracts.py --validate`
- `uv run --with pytest --with jsonschema --with-requirements requirements/ops-portal.txt python -m pytest tests/test_capability_contracts.py tests/test_platform_manifest.py tests/test_interactive_ops_portal.py -q`
- `./scripts/validate_repo.sh data-models generated-portals agent-standards`
- `make generate-platform-manifest`
- `make live-apply-service service=ops_portal env=production`

## Outcome

- The repo now carries one machine-readable capability contract catalog in `config/capability-contract-catalog.json`, with a matching schema, validator, manifest publication path, and ops-portal rendering surface.
- Operator runbooks now document the contract-first workflow before critical shared product choice, so new service onboarding and manifest updates point at the governed catalog instead of product-first fields.
- The focused regression slice passed on the rebased merged-main candidate with `13 passed in 0.89s`, and the repository validation path succeeded for `scripts/capability_contracts.py --validate`, workstream ownership validation, and `./scripts/validate_repo.sh data-models generated-portals agent-standards`.

## Mainline Integration

- ADR 0208 landed on `origin/main` first, so ADR 0205 was recut and released as `0.177.41` on top of that newer mainline instead of the earlier `0.177.40` candidate.
- The governed replay used the ADR 0191 immutable-guest replacement planning path first, confirming `preview_guest` with a `180m` rollback window before the live run.
- The final merged-main replay `make live-apply-service service=ops_portal env=production ALLOW_IN_PLACE_MUTATION=true` completed with `docker-runtime ok=99 changed=3 failed=0`, and the public edge remained healthy with `https://ops.example.com/health` returning `{"status":"ok"}` while `https://ops.example.com/` still redirected to the existing OAuth sign-in boundary.

## Merge Criteria

- every committed capability contract captures outcomes, inputs, outputs, security, audit, observability, portability, migration, and failure handling
- the manifest and interactive ops portal render contract-first capability visibility without breaking existing operator surfaces
- the workstream records live-apply evidence and clearly notes the protected integration files that still wait for merge-to-main

## Remaining For Merge To `main`

- None. The protected integration files and canonical live-apply truth were updated during the merged-main `0.177.41` integration step.
