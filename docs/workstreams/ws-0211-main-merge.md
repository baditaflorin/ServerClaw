# Workstream ws-0211-main-merge

- ADR: [ADR 0211](../adr/0211-shared-policy-packs-and-rule-registries.md)
- Title: Integrate ADR 0211 shared policy registries into `origin/main`
- Status: merged
- Branch: `codex/ws-0211-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0211-main-merge`
- Owner: codex
- Depends On: `ws-0211-live-apply`
- Conflicts With: none

## Purpose

Carry the verified ADR 0211 workstream into the latest `origin/main`, refresh the protected integration files, replay the governed `headscale` production path from the merged candidate, and push the final canonical state only after the release and live-apply evidence both verify cleanly.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0211-main-merge.md`
- `README.md`
- `VERSION`
- `changelog.md`
- `versions/stack.yaml`
- `docs/adr/0211-shared-policy-packs-and-rule-registries.md`
- `docs/workstreams/adr-0211-shared-policy-packs-and-rule-registries.md`
- `docs/runbooks/capacity-model.md`
- `docs/runbooks/capacity-classes.md`
- `docs/runbooks/service-redundancy-tier-matrix.md`
- `docs/runbooks/failure-domain-policy.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `config/shared-policy-packs.json`
- `docs/schema/shared-policy-packs.schema.json`
- `scripts/dependency_graph.py`
- `scripts/generate_dependency_diagram.py`
- `scripts/generate_docs_site.py`
- `scripts/shared_policy_packs.py`
- `scripts/service_redundancy.py`
- `scripts/standby_capacity.py`
- `scripts/capacity_report.py`
- `scripts/failure_domain_policy.py`
- `scripts/environment_topology.py`
- `scripts/validate_repository_data_models.py`
- `tests/test_dependency_graph.py`
- `docs/adr/.index.yaml`
- `docs/site-generated/architecture/dependency-graph.md`
- `receipts/ops-portal-snapshot.html`
- `receipts/live-applies/2026-03-28-adr-0211-shared-policy-packs-and-rule-registries-live-apply.json`
- `receipts/live-applies/2026-03-28-adr-0211-shared-policy-packs-and-rule-registries-mainline-live-apply.json`

## Plan

- cut the protected release/canonical-truth updates from the latest `origin/main` integration branch
- replay the governed `headscale` production path from the merged candidate
- rerun the focused validation and generated-artifact gates with the final integrated state
- record the canonical mainline live-apply receipt and push the completed `main` update

## Result

- After absorbing the concurrent ADR 0209 `0.177.38` mainline integration, ADR 0211 was recut as release `0.177.39`, updating the protected integration files and marking `ws-0211-live-apply` as included in that repo release.
- The merged-main `headscale` replay completed successfully with `localhost ok=16 changed=0 failed=0`, `nginx-lv3 ok=71 changed=3 failed=0`, and `proxmox_florin ok=42 changed=0 failed=0`.
- The public health path `https://headscale.lv3.org/health` still returned `HTTP 200` after the merged-main replay, preserving the shared edge security headers and crawl policy.
- The full repository automation bundle now passes from the integrated main-merge worktree: `./scripts/validate_repo.sh data-models generated-docs generated-portals agent-standards`, `git diff --check`, plus the expanded regression slice `tests/test_dependency_graph.py` and the ADR 0211 policy-registry tests (`33 passed in 1.48s` on the rebased `0.177.39` candidate).
- Final merge verification also harmonized the dependency-graph page renderer used by `scripts/generate_dependency_diagram.py` and `scripts/generate_docs_site.py`, refreshed `docs/diagrams/agent-coordination-map.excalidraw`, and fixed the strict-docs reference in `docs/runbooks/platform-operations-portal.md`, so generated-doc and generated-portal validation now agree on the same committed artifacts.
- The branch-local receipt remains preserved for history, while `receipts/live-applies/2026-03-28-adr-0211-shared-policy-packs-and-rule-registries-mainline-live-apply.json` is the canonical evidence for the integrated `0.177.39` mainline state.
