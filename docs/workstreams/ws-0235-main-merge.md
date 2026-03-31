# Workstream ws-0235-main-merge

- ADR: [ADR 0235](../adr/0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher.md)
- Title: Integrate ADR 0235 cross-application launcher into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.70
- Platform Version Observed During Merge: 0.130.48
- Release Date: 2026-03-29
- Branch: `codex/ws-0235-main-merge-r3`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0235-main-merge-r3`
- Owner: codex
- Depends On: `ws-0235-live-apply`

## Purpose

Carry the verified ADR 0235 launcher rollout onto the latest `origin/main`
after ADR 0248 claimed release `0.177.69`, cut the next protected release,
replay the integrated ops-portal service from the refreshed exact-main
candidate, and promote a canonical mainline receipt for the launcher rollout
without rewriting the earlier isolated-worktree live-apply evidence.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0235-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.70.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/.index.yaml`
- `docs/adr/0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher.md`
- `docs/workstreams/ws-0235-live-apply.md`
- `docs/runbooks/platform-operations-portal.md`
- `scripts/ops_portal/app.py`
- `scripts/ops_portal/runtime_assurance.py`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `tests/test_interactive_ops_portal.py`
- `tests/test_ops_portal_runtime_role.py`
- `tests/test_runtime_assurance_scoreboard.py`
- `receipts/live-applies/2026-03-29-adr-0235-cross-application-launcher-live-apply.json`
- `receipts/live-applies/2026-03-29-adr-0235-cross-application-launcher-mainline-live-apply.json`

## Verification

- `git fetch origin main --prune` confirmed this integration worktree stayed
  aligned with `origin/main` commit
  `414c0b27f424a95bba790963d59cd7a7442ab833` before the protected release cut.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "platform version advances to 0.130.48 after the exact-main ADR 0235 replay re-verifies the PatternFly-style cross-application launcher and session-scoped favorites on ops.lv3.org while preserving the authenticated edge contract on top of the 0.130.47 baseline" --released-on 2026-03-29 --dry-run`
  reported `Current version: 0.177.69`, `Next version: 0.177.70`, and
  `Unreleased notes: 1`.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "platform version advances to 0.130.48 after the exact-main ADR 0235 replay re-verifies the PatternFly-style cross-application launcher and session-scoped favorites on ops.lv3.org while preserving the authenticated edge contract on top of the 0.130.47 baseline" --released-on 2026-03-29`
  prepared release `0.177.70`.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=ops_portal env=production EXTRA_ARGS='-e bypass_promotion=true -e ops_portal_repo_root=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0235-main-merge-r3'`
  completed successfully with final recap
  `docker-runtime-lv3 ok=129 changed=15 failed=0 skipped=14`.
- Fresh mainline evidence was captured in
  `receipts/live-applies/evidence/2026-03-29-adr-0235-mainline-internal-endpoints.txt`,
  `receipts/live-applies/evidence/2026-03-29-adr-0235-mainline-launcher-session-check.txt`,
  `receipts/live-applies/evidence/2026-03-29-adr-0235-mainline-live-hashes.txt`,
  and
  `receipts/live-applies/evidence/2026-03-29-adr-0235-mainline-public-edge-check.txt`,
  covering internal health and launcher rendering, session-scoped favorites,
  the `service:keycloak` redirect flow, deployed runtime hashes, and the
  authenticated public-edge contract.
- Repo automation and validation coverage from this worktree has already
  completed for:
  `uv run --with pytest --with pyyaml --with jsonschema --with fastapi==0.116.1 --with httpx==0.28.1 --with cryptography==45.0.6 --with PyJWT==2.10.1 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest tests/test_interactive_ops_portal.py tests/test_ops_portal_runtime_role.py tests/test_ops_portal.py tests/test_runtime_assurance_scoreboard.py -q`,
  which returned `31 passed in 8.20s`;
  `make syntax-check-ops-portal`;
  `./scripts/validate_repo.sh agent-standards`;
  `make validate-data-models` after removing the temporary ws-0235
  ownership-manifest receipt-path duplication;
  `./scripts/validate_repo.sh generated-docs`;
  `./scripts/validate_repo.sh generated-portals`;
  `uvx --from pyyaml python scripts/canonical_truth.py --check`;
  `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`;
  `uv run --with pyyaml python scripts/generate_diagrams.py --check`;
  `uv run --with pyyaml --with jsonschema python scripts/live_apply_receipts.py --validate`;
  and `git diff --check`, all of which passed.
- `./scripts/validate_repo.sh workstream-surfaces` was exercised from this
  worktree and failed with the expected branch-scoped guard:
  `branch 'codex/ws-0235-main-merge-r3' maps to terminal workstream 'ws-0235-main-merge'`.
  That validator intentionally rejects terminal workstreams on non-`main`
  branches, so the result documents branch behavior rather than a repo-truth
  defect in the merged launcher surfaces.

## Outcome

- release `0.177.70` carries ADR 0235 onto `main`
- the exact-main replay advanced the integrated platform baseline to
  `0.130.48`
- `receipts/live-applies/2026-03-29-adr-0235-cross-application-launcher-mainline-live-apply.json`
  is the canonical integrated receipt for the launcher rollout, while
  `receipts/live-applies/2026-03-29-adr-0235-cross-application-launcher-live-apply.json`
  remains the first isolated-worktree live-apply proof
