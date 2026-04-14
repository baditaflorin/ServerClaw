# Workstream ws-0368-live-apply

- ADR: [ADR 0368](../adr/0368-docker-compose-jinja2-macro-library.md)
- Status: ready
- Branch: `codex/ws-0368-main-integration-r3`
- Worktree: `.worktrees/ws-0368-main-integration-r3`
- Base: `origin/main@6aeb26434724680c6da2162cd3544031b5a93f03` (`VERSION` `0.178.137`)

## Purpose

Close the remaining ADR 0368 gap from the latest realistic `origin/main` base:
finish the exact-main replay repairs, re-run the governed live-apply path for
the services that still surfaced runtime drift, verify the repo automation path
end to end, and leave merge-safe evidence in git-visible state.

## What Changed

- Repaired the Redpanda readiness probe source in
  `catalog/services/redpanda/service.yaml` so it reads back from the produced
  Kafka offset instead of hard-coding `offset=0`, then regenerated
  `config/health-probe-catalog.json`.
- Hardened the shared-worktree receipt path handling in
  `scripts/sbom_scanner.py`, `scripts/managed_image_gate.py`, and
  `scripts/upgrade_container_image.py`, with focused coverage in
  `tests/test_sbom_scanner.py` and `tests/test_upgrade_container_image.py`.
- Refreshed `config/image-catalog.json` plus the Redpanda scan receipts so the
  current catalog points at branch-carried evidence instead of the dirty shared
  root checkout.
- Updated the ws-0368 ownership manifest so the new Redpanda catalog source,
  scan receipts, and live-apply evidence paths are explicitly claimed.

## Verification

- Focused pytest slice passed with `46 passed in 1.05s`:
  - `tests/test_gitea_runtime_role.py`
  - `tests/test_minio_runtime_role.py`
  - `tests/test_redpanda_runtime_role.py`
  - `tests/test_service_definition_catalog.py`
  - `tests/test_sbom_scanner.py`
  - `tests/test_upgrade_container_image.py`
- `./scripts/validate_repo.sh agent-standards service-definitions health-probes data-models workstream-surfaces`
  passed; see
  `receipts/live-applies/evidence/2026-04-14-ws-0368-repo-gates-r1-0.178.137.txt`.
- `git diff --check` passed; see
  `receipts/live-applies/evidence/2026-04-14-ws-0368-git-diff-check-r1-0.178.137.txt`.
- `make check-build-server` passed and confirmed immutable snapshot dry-run
  upload; see
  `receipts/live-applies/evidence/2026-04-14-ws-0368-check-build-server-r1-0.178.137.txt`.
- `make remote-validate` first failed on the remote builder because runner
  images under `registry.example.com` could not be resolved there, then
  completed through the governed local fallback with all blocking checks passed:
  `workstream-surfaces`, `agent-standards`, `ansible-syntax`,
  `schema-validation`, `atlas-lint`, `policy-validation`, `iac-policy-scan`,
  `alert-rule-validation`, `type-check`, and `dependency-graph`. Evidence:
  `receipts/live-applies/evidence/2026-04-14-ws-0368-remote-validate-r1-0.178.137.txt`.

## Live Apply Outcome

- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=minio env=production`
  completed successfully, and direct MinIO live/ready probes passed; see
  `receipts/live-applies/evidence/2026-04-14-ws-0368-minio-verify-r1-0.178.137.txt`.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=gitea env=production`
  completed successfully, and the private Gitea API plus release-bundle
  validation passed; see
  `receipts/live-applies/evidence/2026-04-14-ws-0368-gitea-verify-r1-0.178.137.txt`.
- The first Redpanda replay exposed the stale readiness probe bug. After the
  catalog fix, `ALLOW_IN_PLACE_MUTATION=true make live-apply-service
  service=redpanda env=production` completed successfully, and direct Kafka plus
  schema-registry smoke verification passed; see
  `receipts/live-applies/evidence/2026-04-14-ws-0368-redpanda-verify-r1-0.178.137.txt`.
- ADR 0368 can now truthfully claim `Implementation Status: Live applied`,
  `Implemented In Platform Version: 0.178.137`, and `Implemented On:
  2026-04-14`.

## Remaining Mainline Work

- Fast-forward onto the latest `origin/main` again immediately before merge.
- Replay the merged main tree so `VERSION`, `changelog.md`, `README.md`, and
  `versions/stack.yaml` can be updated from truthful mainline state.
- Push the resulting `main` commit to `origin/main` and remove this worktree.
