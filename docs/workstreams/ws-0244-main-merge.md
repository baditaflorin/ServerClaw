# Workstream WS-0244: Mainline Integration

- ADR: [ADR 0244](../adr/0244-runtime-assurance-matrix-per-service-and-environment.md)
- Title: Integrate ADR 0244 runtime assurance matrix into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.79
- Platform Version Observed During Merge: 0.130.54
- Release Date: 2026-03-29
- Branch: `codex/ws-0244-main-merge-r3`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0244-main-merge-r3`
- Owner: codex
- Depends On: `ws-0244-live-apply`

## Purpose

Carry the verified ADR 0244 live apply onto the latest `origin/main`, refresh
the protected canonical-truth surfaces, and preserve exact-main verification
for the authenticated API gateway plus ops portal runtime-assurance flow.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0244-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.79.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/adr/.index.yaml`
- `docs/adr/0244-runtime-assurance-matrix-per-service-and-environment.md`
- `docs/workstreams/ws-0244-live-apply.md`
- `docs/runbooks/runtime-assurance-matrix.md`
- `config/runtime-assurance-matrix.json`
- `docs/schema/runtime-assurance-matrix.schema.json`
- `scripts/runtime_assurance.py`
- `scripts/api_gateway/main.py`
- `scripts/ops_portal/app.py`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/tasks/verify.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `tests/test_runtime_assurance.py`
- `tests/test_api_gateway.py`
- `tests/test_api_gateway_runtime_role.py`
- `tests/test_interactive_ops_portal.py`
- `tests/test_ops_portal_runtime_role.py`
- `receipts/live-applies/2026-03-29-adr-0244-runtime-assurance-matrix-live-apply.json`

## Verification

- `git fetch origin` kept this worktree current while other workstreams were
  active; immediately before the protected-surface integration the branch was
  ahead of `origin/main` by `11` commits and `origin/main` still pointed at
  release `0.177.78`.
- The exact-main validation slice passed on `codex/ws-0244-main-merge-r3`,
  including the focused runtime-assurance pytest coverage,
  `uv run --with pyyaml --with jsonschema --with nats-py==2.11.0 python3 scripts/runtime_assurance.py --validate --print-report-json`,
  `make validate-data-models`, `make syntax-check-api-gateway`,
  `make preflight WORKFLOW=converge-api-gateway`,
  `make preflight WORKFLOW=converge-ops-portal`, and
  `./scripts/validate_repo.sh agent-standards`.
- `make converge-api-gateway` and `make converge-ops-portal` both completed
  successfully from the latest `origin/main`-based worktree after the gateway
  receipt-sync hang and verify-token fallback defects were fixed in the
  repo-managed roles.
- Live verification on `docker-runtime-lv3` confirmed the guest and container
  hashes matched the branch for both `api_gateway/main.py` and
  `ops_portal/app.py`, the authenticated gateway route returned `HTTP 200`
  with `45` bindings (`8` pass / `37` degraded / `0` failed / `0` unknown),
  and the portal partial rendered the same governed summary with `HTTP 200`,
  visible bindings, and no degraded-data banner.
- The strengthened verify caught a real concurrent replay race when another
  worktree briefly restored an older `api_gateway/main.py` without
  `/v1/platform/runtime-assurance`; the exact-main replay corrected that live
  drift before release.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "platform version advances to 0.130.54 because current main now carries the ADR 0244 runtime-assurance matrix replay verified end to end on docker-runtime-lv3 through the authenticated API gateway and the interactive ops portal" --released-on 2026-03-29`
  prepared release `0.177.79` with the single ws-0244 changelog note.

## Outcome

- Release `0.177.79` carries ADR 0244 onto `main`.
- Platform version `0.130.54` is the first integrated mainline version that
  records the exact-main runtime-assurance replay as canonical truth.
- The canonical live evidence for both `api_gateway` and `ops_portal` now
  points at
  `receipts/live-applies/2026-03-29-adr-0244-runtime-assurance-matrix-live-apply.json`.
