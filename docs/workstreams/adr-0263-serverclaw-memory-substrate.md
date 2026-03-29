# Workstream ADR 0263: ServerClaw Memory Substrate

- ADR: [ADR 0263](../adr/0263-qdrant-postgresql-and-local-search-as-the-serverclaw-memory-substrate.md)
- Title: Implement the governed ServerClaw memory contract on the live private
  retrieval runtime
- Status: live_applied
- Implemented In Repo Version: 0.177.90
- Live Applied In Platform Version: 0.130.60
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0263-mainline-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0263-mainline`
- Owner: codex
- Depends On: `adr-0121-local-search-and-indexing-fabric`,
  `adr-0198-qdrant-vector-search-semantic-rag`,
  `adr-0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0263-qdrant-postgresql-and-local-search-as-the-serverclaw-memory-substrate.md`,
  `docs/workstreams/adr-0263-serverclaw-memory-substrate.md`,
  `docs/runbooks/serverclaw-memory-substrate.md`,
  `docs/runbooks/rag-platform-context.md`,
  `docs/runbooks/platform-api-error-codes.md`, `docs/adr/.index.yaml`,
  `config/error-codes.yaml`, `migrations/0017_serverclaw_memory_schema.sql`,
  `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`,
  `platform/memory/`, `scripts/platform_context_service.py`,
  `scripts/lv3_cli.py`, `requirements/platform-context-api.txt`,
  `collections/ansible_collections/lv3/platform/roles/rag_context_runtime/`,
  `playbooks/rag-context.yml`, `tests/test_platform_context_service.py`,
  `tests/test_lv3_cli.py`, `tests/test_generate_platform_vars.py`,
  `workstreams.yaml`

## Scope

- implement the ServerClaw memory contract on top of the existing private
  platform-context runtime
- store canonical structured memory objects in PostgreSQL with explicit scope,
  provenance, retention, consent, and refresh metadata
- store semantic recall in a dedicated Qdrant collection on the live
  `docker-runtime-lv3` substrate
- materialize a local keyword index for exact recall using the repo-managed
  local search fabric package
- expose governed create, list, get, delete, and hybrid query operations
- verify the full path on production and record durable live-apply evidence

## Non-Goals

- publishing the memory substrate on the public edge
- claiming the full end-user ServerClaw product stack is live
- changing protected release surfaces on this workstream branch before the
  final integration step

## Expected Repo Surfaces

- `docs/adr/0263-qdrant-postgresql-and-local-search-as-the-serverclaw-memory-substrate.md`
- `docs/workstreams/adr-0263-serverclaw-memory-substrate.md`
- `docs/runbooks/serverclaw-memory-substrate.md`
- `docs/runbooks/rag-platform-context.md`
- `docs/runbooks/platform-api-error-codes.md`
- `docs/adr/.index.yaml`
- `config/error-codes.yaml`
- `migrations/0017_serverclaw_memory_schema.sql`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `platform/memory/`
- `scripts/platform_context_service.py`
- `scripts/lv3_cli.py`
- `requirements/platform-context-api.txt`
- `collections/ansible_collections/lv3/platform/roles/rag_context_runtime/`
- `playbooks/rag-context.yml`
- `tests/test_platform_context_service.py`
- `tests/test_lv3_cli.py`
- `tests/test_generate_platform_vars.py`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-runtime-lv3` private platform-context runtime serves a governed
  ServerClaw memory API on the existing `:8010` private endpoint
- `postgres-lv3` contains the canonical `memory.entries` schema used by the
  runtime
- the live runtime maintains a dedicated Qdrant memory collection plus a local
  keyword-search index for the same memory objects

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_rag_context_runtime_role.py tests/test_generate_platform_vars.py -q`
- `uv run --with pytest --with pyyaml --with fastapi --with qdrant-client --with psycopg[binary] python -m pytest tests/test_platform_context_service.py tests/test_lv3_cli.py -q`
- `make syntax-check-rag-context`
- `./scripts/validate_repo.sh data-models workstream-surfaces agent-standards`
- `make remote-validate`
- `make live-apply-service service=rag-context env=production`
- `uv run --with pyyaml python3 scripts/live_apply_receipts.py --validate`

## Live Apply Outcome

- The exact-main replay succeeded from source commit
  `7fe9af77cf7b842884533dde6b2b1af64857fe0d` on top of `origin/main`
  commit `bae420263872e079fdc34f7f755a6984a3cd5949`
  (`VERSION` `0.177.87`, integrated platform baseline `0.130.59`), with final
  recap `docker-runtime-lv3 ok=119 changed=19 failed=0 skipped=21` and
  `proxmox_florin ok=42 changed=7 failed=0 skipped=15`.
- The workstream fixed the replay blockers surfaced by earlier attempts: the
  runtime image now ships the ServerClaw memory bootstrap module, the recovery
  path prefers a host-network classic Docker build before compose startup on
  `docker-runtime-lv3`, and the replay guidance now calls out stale
  `platform-context_default` and `ollama_default` network cleanup when Docker
  bridge state drifts.
- Focused regression and repo-facing validation passed on the workstream head:
  the targeted ADR 0263 pytest slice passed (`31 passed`), the `rag-context`
  syntax check passed, the workstream/data-model/agent-standards repository
  validators passed, and `scripts/live_apply_receipts.py --validate` accepted
  the durable mainline receipt.
- External post-apply verification through `http://100.64.0.1:8010` returned a
  healthy `healthz` response, cited
  `docs/adr/0198-qdrant-vector-search-semantic-rag.md` through
  `lv3_cli.py query-platform-context`, and verified create/query/delete for
  memory id `1f03ab41-1e97-4537-896e-4e7bd3ae2693` with both `semantic` and
  `keyword` recall.

## Live Apply Evidence

- Receipt: `receipts/live-applies/2026-03-29-adr-0263-serverclaw-memory-substrate-mainline-live-apply.json`
- Evidence log: `receipts/live-applies/evidence/2026-03-29-adr-0263-serverclaw-memory-substrate-mainline-live-apply.txt`
- Exact-main replay source commit: `7fe9af77cf7b842884533dde6b2b1af64857fe0d`
- Mainline base included in that replay: `origin/main` commit `bae420263`
- Repo version context: `0.177.87`
- LV3 run id: `e6fa9fca7a534939928bc8c0938756b2`
- ansible scope run id: `9e8dcfe46d20419fb39c464891acd29c`
- trace id: `3a088906b6a84a9bae17eb26dac49daf`
- Replay recap: `docker-runtime-lv3 ok=119 changed=19 failed=0`, `proxmox_florin ok=42 changed=7 failed=0`
- External post-apply verification through `http://100.64.0.1:8010` returned `healthz.status=ok`, cited `docs/adr/0198-qdrant-vector-search-semantic-rag.md` through `lv3_cli.py query-platform-context`, and verified memory id `1f03ab41-1e97-4537-896e-4e7bd3ae2693` through CLI create/query/delete with both `semantic` and `keyword` recall.

## Merge Criteria

- the live private runtime persists structured memory objects in PostgreSQL
- semantic recall and keyword recall both resolve against the same governed
  memory object set
- scope, provenance, retention, consent, and refresh metadata are required for
  durable memory objects
- live apply is verified end to end with durable receipt evidence and ADR
  metadata is updated to implemented truth

## Mainline Integration Outcome

- Release `0.177.90` was cut on 2026-03-29 from the merged mainline
  integration worktree.
- `VERSION`, `changelog.md`, `README.md`, `RELEASE.md`,
  `docs/release-notes/`, `versions/stack.yaml`, and `workstreams.yaml` now
  record ADR 0263 as integrated mainline truth, and
  `versions/stack.yaml.live_apply_evidence.latest_receipts.serverclaw_memory`
  points at
  `2026-03-29-adr-0263-serverclaw-memory-substrate-mainline-live-apply`.
- The integrated platform version advanced to `0.130.60` after the exact-main
  replay and verification completed.

## Replay Lessons

- keep this work on the private `rag-context` lane unless a later ADR explicitly
  promotes the memory substrate behind the shared API gateway
- prefer the host-network classic Docker build path before `docker compose up`
  on `docker-runtime-lv3`; earlier `compose up --build` replays were not
  reliable on this host
- treat stale `platform-context_default` and `ollama_default` Docker networks as
  a first-class recovery clue when compose reports missing bridge devices during
  an exact-main replay
