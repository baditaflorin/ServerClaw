# Workstream ws-0268-main-integration

- ADR: [ADR 0268](../adr/0268-fresh-worktree-bootstrap-manifests-for-generated-artifacts-and-local-inputs.md)
- Title: Integrate ADR 0268 exact-main replay onto `origin/main`
- Status: `in_progress`
- Included In Repo Version: 0.177.81
- Platform Version Observed During Integration: 0.130.54
- Release Date: 2026-03-29
- Branch: `codex/ws-0268-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0268-main-integration`
- Owner: codex
- Depends On: `ws-0268-live-apply`

## Purpose

Carry the verified ADR 0268 fresh-worktree bootstrap implementation onto the
latest available `origin/main`, refresh the protected release and
canonical-truth surfaces for repository version `0.177.81`, and then record
the exact-main production replay that turns the branch-local receipt into the
canonical mainline evidence.

## Shared Surfaces

- `workstreams.yaml`
- `.config-locations.yaml`
- `Makefile`
- `mkdocs.yml`
- `config/ansible-execution-scopes.yaml`
- `config/command-catalog.json`
- `config/correction-loops.json`
- `config/workflow-catalog.json`
- `config/worktree-bootstrap-manifests.json`
- `docs/adr/0094-developer-portal-and-documentation-site.md`
- `docs/runbooks/controller-local-secrets-and-preflight.md`
- `docs/runbooks/playbook-execution-model.md`
- `docs/release-process.md`
- `docs/workstreams/ws-0268-main-integration.md`
- `docs/workstreams/ws-0268-live-apply.md`
- `docs/adr/0268-fresh-worktree-bootstrap-manifests-for-generated-artifacts-and-local-inputs.md`
- `docs/adr/.index.yaml`
- `docs/site-generated/architecture/dependency-graph.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.81.md`
- `versions/stack.yaml`
- `receipts/ops-portal-snapshot.html`
- `receipts/live-applies/2026-03-29-adr-0268-fresh-worktree-bootstrap-manifests-live-apply.json`
- `receipts/live-applies/2026-03-29-adr-0268-fresh-worktree-bootstrap-manifests-mainline-live-apply.json`
- `scripts/generate_docs_site.py`
- `scripts/preflight_controller_local.py`
- `scripts/workflow_catalog.py`
- `scripts/worktree_bootstrap.py`
- `tests/test_docs_site.py`
- `tests/test_preflight_controller_local.py`
- `tests/test_service_id_resolver.py`

## Verification

- `git fetch origin --prune` confirmed the newest available `origin/main`
  baseline is commit `9416fec683e90bf340baf54ec9eb70df84e57482`.
- The integrated worktree cherry-picked the ADR 0268 implementation commit and
  the branch-local live-apply receipt onto that baseline before cutting the
  protected release files for `0.177.81`.
- `uv run --with pyyaml python scripts/generate_adr_index.py --write`,
  `uv run --with pyyaml python scripts/canonical_truth.py --write`, and
  `uv run --with pyyaml python scripts/workflow_catalog.py --validate` all
  completed successfully on the integration worktree.
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
  and `git diff --check` both passed before the exact-main replay.
- `./scripts/validate_repo.sh agent-standards` reached the expected branch
  registration warning that this workstream file and registry entry resolve.

## Remaining

- commit the protected release and metadata surfaces for repository version
  `0.177.81`
- replay the merged-main production edge publication from that release commit
- record the canonical mainline receipt, advance the platform version, and push
  `origin/main`
