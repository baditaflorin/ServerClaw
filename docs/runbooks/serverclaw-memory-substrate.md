# ServerClaw Memory Substrate

This runbook covers ADR 0263 and the private ServerClaw memory substrate hosted
inside the `rag-context` runtime on `docker-runtime`.

- ADR: [docs/adr/0263-qdrant-postgresql-and-local-search-as-the-serverclaw-memory-substrate.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0263-qdrant-postgresql-and-local-search-as-the-serverclaw-memory-substrate.md)
- Runtime lane: `make live-apply-service service=rag-context env=production`
- Private API base URL: `http://100.64.0.1:8010`
- Auth token file: `.local/platform-context/api-token.txt`

## What It Stores

- PostgreSQL keeps the canonical structured memory objects in `memory.entries`.
- Qdrant keeps semantic recall in the `serverclaw_memory` collection.
- The local search fabric keeps keyword recall in the generated index at
  `/opt/platform-context/memory-search-index/documents.json`.

Every durable memory object must include:

- `scope_kind` and `scope_id`
- `object_type`
- `provenance`
- `retention_class`
- `consent_boundary`
- `last_refreshed_at`

Optional fields include `delegation_boundary`, `source_uri`, `metadata`, and
`expires_at`.

## Normal Operator Flow

Create or update one memory object:

```bash
python3 scripts/lv3_cli.py memory put \
  --scope-kind workspace \
  --scope-id ops-smoke \
  --object-type note \
  --title "ADR 0263 smoke memory substrate" \
  --content "ServerClaw memory substrate smoke entry for qdrant semantic recall and local keyword search." \
  --provenance manual-test \
  --retention-class smoke \
  --consent-boundary test-only
```

Query hybrid recall for one scope:

```bash
python3 scripts/lv3_cli.py memory query "serverclaw memory substrate smoke qdrant local search" \
  --scope-kind workspace \
  --scope-id ops-smoke \
  --object-type note \
  --limit 3
```

List or fetch the stored object:

```bash
python3 scripts/lv3_cli.py memory list --scope-kind workspace --scope-id ops-smoke --object-type note
python3 scripts/lv3_cli.py memory get <memory-id>
```

Delete the temporary object when verification is complete:

```bash
python3 scripts/lv3_cli.py memory delete <memory-id>
```

## Direct API Checks

Create one entry:

```bash
curl -fsS \
  -H "Authorization: Bearer $(cat .local/platform-context/api-token.txt)" \
  -H "Content-Type: application/json" \
  -X POST http://100.64.0.1:8010/v1/memory/entries \
  -d '{
    "scope_kind": "workspace",
    "scope_id": "ops-smoke",
    "object_type": "note",
    "title": "ADR 0263 smoke memory substrate",
    "content": "ServerClaw memory substrate smoke entry for qdrant semantic recall and local keyword search.",
    "provenance": "manual-test",
    "retention_class": "smoke",
    "consent_boundary": "test-only"
  }'
```

Query hybrid recall:

```bash
curl -fsS \
  -H "Authorization: Bearer $(cat .local/platform-context/api-token.txt)" \
  -H "Content-Type: application/json" \
  -X POST http://100.64.0.1:8010/v1/memory/query \
  -d '{
    "query": "serverclaw memory substrate smoke qdrant local search",
    "scope_kind": "workspace",
    "scope_id": "ops-smoke",
    "object_type": "note",
    "limit": 3
  }'
```

The top match should show:

- the created `memory_id`
- `matched_backends` containing both `semantic` and `keyword`
- the expected `scope_kind`, `scope_id`, and `object_type`

## Recovery

Replay the full governed lane:

```bash
make live-apply-service service=rag-context env=production
```

If the runtime is healthy but memory calls fail:

1. Confirm the database schema exists:

```bash
ssh ops@100.64.0.1 -- sudo -u postgres psql -d windmill -Atqc "SELECT to_regclass('memory.entries')"
```

2. Confirm the private runtime env includes the memory settings:

```bash
ssh ops@100.64.0.1 -- sudo grep '^PLATFORM_CONTEXT_MEMORY_' /opt/platform-context/runtime.env
```

3. Re-run the smoke create/query/delete flow through `lv3 memory`.

If semantic recall is missing but keyword recall still works, replay the same
`rag-context` live apply first so the runtime can re-render the service image
and the dedicated `serverclaw_memory` collection.

If the replay reaches `Build the platform context API image with host
networking` and Docker 29 returns a BuildKit-side `error reading from server:
EOF`, keep the role-managed host-network classic-builder path in place. ADR
0263 now forces `DOCKER_BUILDKIT=0` and `COMPOSE_DOCKER_CLI_BUILD=0`, runs
`docker build --network host` first, and only then starts the compose stack
with `--no-build` on `docker-runtime`.

If Docker restarts drop the `DOCKER` nat chain before the stack start, rerun the
repo-managed live apply. ADR 0263 now restarts Docker, rechecks the nat chain,
and waits for `docker info` before trying to recreate the published
platform-context ports.

If the build succeeds but `platform-context-api` or `ollama` then fails with
`failed to create endpoint ... network ... does not exist`, treat it as stale
compose-network drift, not as an image defect. Recover the affected stack with
`docker compose down --remove-orphans`, remove the stale
`platform-context_default` or `ollama_default` network if it is still present,
and rerun `docker compose up -d --remove-orphans`. For the platform-context
stack, keep the role-managed explicit `docker build --network host` step in
front and use `docker compose up -d --no-build --force-recreate
--remove-orphans` for the restart so compose does not fall back to the broken
inline build path.
