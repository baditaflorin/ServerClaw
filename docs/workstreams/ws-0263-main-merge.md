# Workstream ws-0263-main-merge

- ADR: [ADR 0263](../adr/0263-qdrant-postgresql-and-local-search-as-the-serverclaw-memory-substrate.md)
- Title: Integrate ADR 0263 exact-main replay onto `origin/main`
- Status: `merged`
- Included In Repo Version: 0.177.90
- Platform Version Observed During Merge: 0.130.60
- Release Date: 2026-03-29
- Branch: `codex/ws-0263-main-push`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0263-main-push`
- Owner: codex
- Depends On: `ws-0263-serverclaw-memory-substrate`

## Purpose

Carry the verified ADR 0263 exact-main replay onto the current `origin/main`,
refresh the protected canonical-truth and generated status surfaces from that
merged baseline, and publish the latest ServerClaw memory receipt without
changing the replay's original source-commit context.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0263-main-merge.md`
- `docs/workstreams/adr-0263-serverclaw-memory-substrate.md`
- `docs/adr/0263-qdrant-postgresql-and-local-search-as-the-serverclaw-memory-substrate.md`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.90.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/runbooks/serverclaw-memory-substrate.md`
- `docs/runbooks/rag-platform-context.md`
- `docs/runbooks/platform-api-error-codes.md`
- `config/error-codes.yaml`
- `inventory/group_vars/platform.yml`
- `migrations/0017_serverclaw_memory_schema.sql`
- `platform/memory/`
- `collections/ansible_collections/lv3/platform/roles/rag_context_runtime/`
- `playbooks/rag-context.yml`
- `requirements/platform-context-api.txt`
- `scripts/generate_platform_vars.py`
- `scripts/platform_context_service.py`
- `scripts/lv3_cli.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_platform_context_service.py`
- `tests/test_lv3_cli.py`
- `tests/test_rag_context_runtime_role.py`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `receipts/live-applies/2026-03-29-adr-0263-serverclaw-memory-substrate-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-29-adr-0263-serverclaw-memory-substrate-mainline-live-apply.txt`

## Verification

- Release `0.177.90` was cut from the merged integration worktree after
  cherry-picking the validated ADR 0263 integration onto the latest fetched
  `origin/main` commit `92c56a075c273dc4b4e2d720ceb5e75c46cb9399`.
- The exact-main replay that backs this merge succeeded from source commit
  `7fe9af77cf7b842884533dde6b2b1af64857fe0d` with
  `docker-runtime-lv3 ok=119 changed=19 failed=0 skipped=21` and
  `proxmox_florin ok=42 changed=7 failed=0 skipped=15`.
- External verification through `http://100.64.0.1:8010` returned
  `{"status":"ok","collection":"platform_context","memory_collection":"serverclaw_memory","memory_enabled":true}`,
  cited `docs/adr/0198-qdrant-vector-search-semantic-rag.md` via
  `lv3_cli.py query-platform-context`, and confirmed memory
  `1f03ab41-1e97-4537-896e-4e7bd3ae2693` through CLI create/query/delete with
  both `keyword` and `semantic` recall.
- `make remote-validate` passed after regenerating
  `docs/diagrams/agent-coordination-map.excalidraw`, clearing the remote
  `agent-standards`, `alert-rule-validation`, `ansible-syntax`,
  `dependency-graph`, `policy-validation`, `schema-validation`, `type-check`,
  and `workstream-surfaces` lanes on the exact merged worktree.
- `make pre-push-gate` passed on the build-server with all blocking checks
  green, including `ansible-lint`, `generated-docs`, `generated-portals`,
  `dependency-graph`, `security-scan`, `tofu-validate`, `packer-validate`, and
  `integration-tests`.
- `make gate-status` reported the latest validation gate run as `passed` at
  `2026-03-29T22:14:40.647834+00:00` via `build-server`.

## Outcome

- Release `0.177.90` carries ADR 0263's exact-main replay onto `main`.
- The integrated platform baseline advanced from `0.130.59` to `0.130.60`
  after the exact-main replay and verification completed.
- `versions/stack.yaml` now points `serverclaw_memory` at
  `2026-03-29-adr-0263-serverclaw-memory-substrate-mainline-live-apply` while
  ADR 0263 itself records `0.177.90` and `0.130.60` as the first repo and
  platform versions where the decision is fully implemented on main.
