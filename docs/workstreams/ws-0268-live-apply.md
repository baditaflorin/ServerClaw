# Workstream ws-0268-live-apply: Live Apply ADR 0268 From Latest `origin/main`

- ADR: [ADR 0268](../adr/0268-fresh-worktree-bootstrap-manifests-for-generated-artifacts-and-local-inputs.md)
- Title: Add bootstrap manifests for generated artifacts and controller-local inputs, then verify the fresh-worktree apply path end to end
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0268-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0268-live-apply`
- Owner: codex
- Depends On: `adr-0034-controller-local-secret-manifest-and-preflight`, `adr-0035-workflow-catalog-and-machine-readable-execution-contracts`, `adr-0079-playbook-decomposition-and-shared-execution-model`, `adr-0167-agent-handoff-and-context-preservation`, `adr-0211-shared-policy-packs-and-rule-registries`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0094-developer-portal-and-documentation-site.md`, `docs/adr/0268-fresh-worktree-bootstrap-manifests-for-generated-artifacts-and-local-inputs.md`, `docs/workstreams/ws-0268-live-apply.md`, `docs/runbooks/controller-local-secrets-and-preflight.md`, `docs/runbooks/playbook-execution-model.md`, `docs/release-process.md`, `.config-locations.yaml`, `Makefile`, `mkdocs.yml`, `config/command-catalog.json`, `config/correction-loops.json`, `config/workflow-catalog.json`, `config/worktree-bootstrap-manifests.json`, `docs/site-generated/architecture/dependency-graph.md`, `receipts/ops-portal-snapshot.html`, `scripts/generate_docs_site.py`, `scripts/preflight_controller_local.py`, `scripts/worktree_bootstrap.py`, `scripts/workflow_catalog.py`, `tests/test_docs_site.py`, `tests/test_preflight_controller_local.py`, `workstreams.yaml`

## Scope

- add a machine-readable bootstrap-manifest catalog for fresh worktrees
- teach the shared controller preflight to materialize missing generated artifacts before a governed run continues
- fail early with precise bootstrap errors when required controller-local files, environment variables, or helper paths are absent
- wire the generic `live-apply-*` entrypoints through the bootstrap preflight and verify the isolated-worktree edge-publication path end to end

## Non-Goals

- replacing the existing controller-local secret manifest
- changing release metadata on this workstream branch before the final integration step
- claiming platform-version advancement before the latest-main replay and verification are complete

## Expected Repo Surfaces

- `config/worktree-bootstrap-manifests.json`
- `config/workflow-catalog.json`
- `Makefile`
- `mkdocs.yml`
- `scripts/preflight_controller_local.py`
- `scripts/generate_docs_site.py`
- `scripts/workflow_catalog.py`
- `scripts/controller_automation_toolkit.py`
- `docs/runbooks/controller-local-secrets-and-preflight.md`
- `docs/runbooks/playbook-execution-model.md`
- `docs/release-process.md`
- `docs/adr/0094-developer-portal-and-documentation-site.md`
- `.config-locations.yaml`
- `docs/site-generated/architecture/dependency-graph.md`
- `receipts/ops-portal-snapshot.html`
- `tests/test_docs_site.py`
- `tests/test_preflight_controller_local.py`
- `docs/adr/0268-fresh-worktree-bootstrap-manifests-for-generated-artifacts-and-local-inputs.md`
- `docs/workstreams/ws-0268-live-apply.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `nginx-lv3` shared edge publication replayed from this isolated worktree after bootstrap preflight materializes the required generated portal artifacts

## Ownership Notes

- this workstream owns the ADR 0268 bootstrap-manifest implementation and its live-apply evidence
- protected release files stay untouched here until the later main integration step
- the final handoff must state exactly which merge-to-main updates remain if the branch-local live apply completes first

## Verification

 - `uv run --with pytest --with-requirements requirements/docs.txt python -m pytest -q tests/test_docs_site.py tests/test_preflight_controller_local.py tests/test_correction_loops.py`
- `uv run --with pyyaml python scripts/workflow_catalog.py --validate`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `./scripts/validate_repo.sh agent-standards`
- `make preflight WORKFLOW=configure-edge-publication`
- `make configure-edge-publication env=production`

## Branch-Local Results

- the isolated worktree started with `build/ops-portal/`, `build/changelog-portal/`, and `build/docs-portal/` all missing
- `make live-apply-service service=public-edge env=staging EXTRA_ARGS=--syntax-check` rebuilt all three generated portals through the new bootstrap preflight and then stopped at `check-canonical-truth`, which is expected on this branch because the protected `README.md` integration summary is intentionally deferred
- `make configure-edge-publication env=production` completed successfully after the repaired bootstrap path, with `nginx-lv3 ok=61 changed=4 failed=0`
- `curl -I https://grafana.lv3.org`, `curl -I https://nginx.lv3.org`, `curl -I https://docs.lv3.org`, and `curl -I https://changelog.lv3.org` all returned healthy responses after the replay
- the branch-local live-apply evidence is recorded in `receipts/live-applies/2026-03-29-adr-0268-fresh-worktree-bootstrap-manifests-live-apply.json`

## Merge Criteria

- fresh worktrees no longer fail late when shared edge publication needs generated portals
- the generic `live-apply-*` entrypoints invoke the bootstrap preflight before mutating anything
- ADR 0268 metadata records repository implementation plus live-apply evidence, while merge-only release files remain deferred until integration

## Notes For The Next Assistant

- verify the committed receipt and ADR metadata match the exact latest `origin/main` commit this worktree started from
- if the latest-main integration step needs protected release-file updates, do them only after the workstream branch has been fully validated and merged cleanly
