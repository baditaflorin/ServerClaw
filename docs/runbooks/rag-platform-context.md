# RAG Platform Context

## Purpose

This runbook converges and verifies the private platform context API introduced by ADR 0070.

The service exposes an OpenAPI tool server backed by Qdrant and a local embedding model. It indexes authoritative repo documents and returns cited retrieval chunks for operational questions.

## Repo Surfaces

- `playbooks/rag-context.yml`
- `roles/rag_context_runtime/`
- `scripts/build_rag_index.py`
- `scripts/query_platform_context.py`
- `scripts/platform_context_corpus.py`
- `scripts/platform_context_service.py`
- `config/agent-tool-registry.json`
- `config/windmill/scripts/rebuild-rag-index.py`

## Delivered Live Surfaces

- private API: `http://100.118.189.95:8010`
- Qdrant storage on `docker-runtime-lv3`
- controller-local bearer token: `.local/platform-context/api-token.txt`
- repo-grounded OpenAPI tool server for Open WebUI global-tool integration

## Commands

Syntax-check the workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-rag-context
```

Converge the private runtime and host-side Tailscale proxy:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-rag-context
```

Rebuild the index from the current repo checkout:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
python3 scripts/build_rag_index.py --api-url http://100.118.189.95:8010 --api-token-file .local/platform-context/api-token.txt
```

Query the private endpoint directly:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
python3 scripts/query_platform_context.py --api-url http://100.118.189.95:8010 --question "how does step-ca issue SSH certificates"
```

Dry-run the chunk build without uploading:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
python3 scripts/build_rag_index.py --dry-run
```

## Verification

1. `curl -s http://100.118.189.95:8010/healthz`
2. `python3 scripts/build_rag_index.py --dry-run`
3. `python3 scripts/query_platform_context.py --api-url http://100.118.189.95:8010 --question "how does step-ca issue SSH certificates"`
4. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker compose --file /opt/platform-context/docker-compose.yml ps && sudo ls -l /opt/platform-context/openbao /run/lv3-secrets/platform-context && sudo test ! -e /opt/platform-context/platform-context.env'`

## Open WebUI Integration

Open WebUI v0.6+ supports shared OpenAPI tool servers as global tools. For this platform:

1. open Open WebUI admin settings
2. add a global tool server pointing at `http://host.docker.internal:8010`
3. configure Bearer authentication with the token from `.local/platform-context/api-token.txt`
4. enable the global tool in the desired chat before use

This follows the Open WebUI global OpenAPI tool-server model rather than exposing arbitrary direct tool servers.

## Corpus and Chunking Rules

- ADRs and runbooks are chunked at Markdown `##` section boundaries first
- large sections are split further by paragraph with overlap
- receipts, catalogs, `versions/stack.yaml`, `VERSION`, and `changelog.md` are included as authoritative supporting context
- each chunk keeps `source_path`, `document_kind`, `document_title`, `section_heading`, and `adr_number` metadata for citation

## Operating Notes

- The API token is required for all query and admin endpoints.
- The current runtime uses a local `sentence-transformers/all-MiniLM-L6-v2` embedding model. Tests may switch to the deterministic `token-hash` backend, but the live runtime should stay on the local model unless a follow-up ADR changes that.
- Windmill seeds `f/lv3/rebuild_rag_index` so the deployed control plane can trigger a local-corpus rebuild without re-reading the full repository through chat context.
