# Workstream ADR 0207: Anti-Corruption Layers At Provider Boundaries

- ADR: [ADR 0207](../adr/0207-anti-corruption-layers-at-provider-boundaries.md)
- Title: Translate critical provider payloads into canonical internal facts and enforce that contract in validation
- Status: implemented
- Branch: `codex/ws-0207-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0207-live-apply`
- Owner: codex
- Depends On: `adr-0206-ports-and-adapters-for-external-integrations`, `adr-0210-canonical-domain-models-over-vendor-schemas`, `adr-0213-architecture-fitness-functions-in-the-validation-gate`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/adr/0207-anti-corruption-layers-at-provider-boundaries.md`, `docs/workstreams/adr-0207-anti-corruption-layers-at-provider-boundaries.md`, `config/provider-boundary-catalog.yaml`, `scripts/provider_boundary_catalog.py`, `config/validation-gate.json`, `scripts/validate_repo.sh`, `collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/`, `collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/`, `docs/runbooks/subdomain-governance.md`, `docs/runbooks/validate-repository-automation.md`, `docs/runbooks/validation-gate.md`
- Ownership Manifest: `workstreams.yaml` `ownership_manifest`

## Scope

- add a repo-managed catalog of provider boundaries that must keep raw provider payloads edge-local
- wire the provider-boundary validation into `make validate`, the remote validation gate, and the Windmill post-merge gate
- refactor the Hetzner DNS roles so matching and drift logic uses canonical DNS facts instead of raw Hetzner response fields
- capture live-apply evidence that the merged-main validation path and a live DNS reconcile both passed

## Non-Goals

- rewriting every service-specific operator CLI around canonical models in one pass
- changing release files on the branch-local workstream path
- changing canonical `versions/stack.yaml` until the final merged-main integration step

## Expected Repo Surfaces

- `docs/adr/0207-anti-corruption-layers-at-provider-boundaries.md`
- `docs/workstreams/adr-0207-anti-corruption-layers-at-provider-boundaries.md`
- `docs/adr/.index.yaml`
- `workstreams.yaml`
- `config/provider-boundary-catalog.yaml`
- `config/ansible-role-idempotency.yml`
- `.config-locations.yaml`
- `scripts/provider_boundary_catalog.py`
- `scripts/validate_repo.sh`
- `config/validation-gate.json`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/README.md`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/tasks/record.yml`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/README.md`
- `platform/ansible/plane.py`
- `docs/runbooks/subdomain-governance.md`
- `docs/runbooks/validate-repository-automation.md`
- `docs/runbooks/validation-gate.md`
- `tests/test_plane_client.py`
- `tests/test_provider_boundary_catalog.py`
- `tests/test_hetzner_dns_record_role.py`
- `tests/test_hetzner_dns_records_role.py`

## Expected Live Surfaces

- live DNS reconciliation through the governed Hetzner DNS role path
- build-server `remote-validate` execution using the merged-main validation manifest
- Windmill post-merge validation from the mirrored worker checkout after the repo sync replay

## Ownership Notes

- the workstream owns the provider-boundary catalog, validator, Hetzner DNS role refactor, and the matching runbook updates
- the workstream also repairs the current-main validation drift in `config/ansible-role-idempotency.yml` so the full repo gate can run honestly while ADR 0207 tightens the merge gate
- the workstream also removes one existing ad hoc retry loop from `platform/ansible/plane.py` so the retry guard no longer blocks the full validation path on current `main`
- this workstream intentionally avoids `VERSION`, numbered `changelog.md` release sections, `README.md` integrated status, and `versions/stack.yaml` until final integration on `main`
- the first implementation assumes the highest-value provider boundary to harden immediately is the Hetzner DNS mutation path because it is shared by many live service converges and is already part of the governed live-apply workflow

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_provider_boundary_catalog.py tests/test_hetzner_dns_record_role.py tests/test_hetzner_dns_records_role.py -q`
- `./scripts/validate_repo.sh data-models`
- `make remote-validate`
- live DNS reconcile from merged `main` using a governed hostname that already exists in the subdomain catalog
- Windmill post-merge gate from `/srv/proxmox_florin_server`

## Merge Criteria

- the provider-boundary catalog fails the repo gate if the Hetzner DNS roles leak raw provider payload selectors past the translation step
- the Hetzner DNS roles only use canonical DNS facts after the provider boundary translation tasks
- the merged-main validation path and the worker post-merge validation path both exercise the new provider-boundary guard successfully
- the workstream records exactly which shared integration updates still belong to the final `main` step

## Notes For The Next Assistant

- if more provider-boundary rollouts follow, extend `config/provider-boundary-catalog.yaml` and the validator instead of cloning one-off grep checks
- treat raw provider payloads as debug-only artifacts; if a new receipt or generated doc needs provider detail, expose it through a canonical field plus an explicitly marked edge-local debug block
