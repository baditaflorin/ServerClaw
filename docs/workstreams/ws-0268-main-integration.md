# Workstream ws-0268-main-integration

- ADR: [ADR 0268](../adr/0268-fresh-worktree-bootstrap-manifests-for-generated-artifacts-and-local-inputs.md)
- Title: Integrate ADR 0268 exact-main replay onto `origin/main`
- Status: `merged`
- Included In Repo Version: 0.177.83
- Platform Version Observed During Integration: 0.130.56
- Release Date: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0268-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0268-main-integration`
- Owner: codex
- Depends On: `ws-0268-live-apply`

## Purpose

Carry the verified ADR 0268 fresh-worktree bootstrap implementation onto the
latest available `origin/main`, refresh the protected release and
canonical-truth surfaces for repository version `0.177.83`, and then record
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
- `scripts/canonical_truth.py`
- `docs/adr/0094-developer-portal-and-documentation-site.md`
- `docs/runbooks/controller-local-secrets-and-preflight.md`
- `docs/runbooks/playbook-execution-model.md`
- `docs/release-process.md`
- `docs/workstreams/ws-0268-main-integration.md`
- `docs/workstreams/ws-0268-live-apply.md`
- `docs/adr/0268-fresh-worktree-bootstrap-manifests-for-generated-artifacts-and-local-inputs.md`
- `docs/adr/.index.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.83.md`
- `versions/stack.yaml`
- `receipts/ops-portal-snapshot.html`
- `receipts/live-applies/2026-03-29-adr-0268-fresh-worktree-bootstrap-manifests-live-apply.json`
- `receipts/live-applies/2026-03-29-adr-0268-fresh-worktree-bootstrap-manifests-mainline-live-apply.json`
- `scripts/generate_docs_site.py`
- `scripts/preflight_controller_local.py`
- `scripts/workflow_catalog.py`
- `scripts/worktree_bootstrap.py`
- `tests/test_docs_site.py`
- `tests/test_canonical_truth.py`
- `tests/test_preflight_controller_local.py`
- `tests/test_service_id_resolver.py`

## Verification

- `git fetch origin --prune` confirmed the newest available `origin/main`
  baseline remained commit `a4f8e6cc894c59e8fb744cc5be9691b96c44702a` while
  the protected release cut advanced repository version `0.177.81` to
  `0.177.82`.
- The exact-main source commit `9e120e0f7d63d8dfd483aedefc5f1cd7430f1824`
  preserved the `public-edge` to `nginx_edge` alias in
  `config/ansible-execution-scopes.yaml`, refreshed the generated ops-portal
  snapshot, and preserved a clean latest-main replay source.
- `make immutable-guest-replacement-plan service=public-edge` confirmed the
  documented ADR 0191 narrow exception rule for `nginx_edge` on `nginx-lv3`,
  including the `inactive_edge_peer` validation mode and the `120m` rollback
  window.
- `scripts/canonical_truth.py` was updated so capability receipt precedence now
  follows the integrated repo version instead of ADR number, allowing the
  newer `0.177.82` exact-main public-edge receipt to override the older
  `0.177.77` edge receipt for `versions/stack.yaml.live_apply_evidence`.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=public-edge env=production`
  rebuilt the missing `build/ops-portal/`, `build/changelog-portal/`, and
  `build/docs-portal/` directories from a clean worktree and completed
  successfully with final recap `nginx-lv3 : ok=61 changed=4 failed=0`.
- `curl -I --max-time 20 https://grafana.lv3.org` returned `HTTP/2 302` to
  `/login`, `curl -I --max-time 20 https://nginx.lv3.org` returned `HTTP/2 200`,
  and both `https://docs.lv3.org` and `https://changelog.lv3.org` returned
  `HTTP/2 302` to their expected `oauth2/sign_in` paths afterward.

## Outcome

- Release `0.177.82` now carries both the ADR 0268 implementation and the
  exact-main wrapper verification onto `main`.
- Platform version `0.130.56` is the first integrated platform version that
  records the canonical `live-apply-service service=public-edge` replay from
  the synchronized latest-main source commit.
- `receipts/live-applies/2026-03-29-adr-0268-fresh-worktree-bootstrap-manifests-mainline-live-apply.json`
  is the canonical exact-main proof, while the branch-local receipt remains
  preserved as the first isolated-worktree replay.
