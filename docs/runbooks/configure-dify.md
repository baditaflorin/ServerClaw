# Configure Dify

This runbook covers the repo-managed Dify deployment introduced by [ADR 0197](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0197-dify-visual-llm-workflow-canvas.md).

## Scope

The Dify workflow converges:

- the PostgreSQL backend for Dify on `postgres`
- the Dify runtime stack on `docker-runtime`
- the public hostname `agents.example.com` on the shared NGINX edge
- the governed Dify tool-provider bridge through `api.example.com`
- controller-local bootstrap artifacts under `.local/dify/`

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- OpenBao is deployed and healthy for compose runtime secret injection
- `langfuse.example.com`, `api.example.com`, and `sso.example.com` are already healthy
- Hetzner DNS API credentials are available when the edge certificate requires expansion

## Converge

Run:

```bash
HETZNER_DNS_API_TOKEN=... make converge-dify
```

When the Hetzner DNS write API is unavailable, replay the runtime without the public edge mutation:

```bash
make converge-dify EXTRA_ARGS='-e dify_skip_edge=true'
```

## Generated Local Artifacts

The workflow maintains controller-local material under `.local/dify/`:

- `database-password.txt`
- `init-password.txt`
- `admin-password.txt`
- `secret-key.txt`
- `redis-password.txt`
- `qdrant-api-key.txt`
- `sandbox-api-key.txt`
- `plugin-daemon-key.txt`
- `plugin-inner-api-key.txt`
- `tools-api-key.txt`
- `export-smoke.yml`

## Verification

Repository and syntax checks:

```bash
make syntax-check-dify
```

Runtime and API verification:

```bash
curl -fsS https://agents.example.com/healthz
```

The public hostname verifies the unauthenticated health path, but the bootstrap and app-management APIs remain OAuth-protected at the edge. Run the smoke flow through a local tunnel to `docker-runtime`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -W %h:%p ops@100.64.0.1" \
  -L 18094:127.0.0.1:8094 ops@10.10.10.20

curl -fsS http://127.0.0.1:18094/healthz
uv run --with requests --with pyyaml python3 scripts/dify_smoke.py \
  --base-url http://127.0.0.1:18094 \
  --admin-email operator@example.com \
  --admin-password-file .local/dify/admin-password.txt \
  --init-password-file .local/dify/init-password.txt \
  --tools-api-key-file .local/dify/tools-api-key.txt
```

The governed tool bridge can be verified independently of the public Dify hostname:

```bash
TOOLS_KEY=$(cat .local/dify/tools-api-key.txt)
curl -sS -X POST https://api.example.com/v1/dify-tools/get-platform-status \
  -H "Content-Type: application/json" \
  -H "X-LV3-Dify-Api-Key: ${TOOLS_KEY}" \
  -d '{}'
```

The smoke script verifies the setup flow, signs in with the bootstrap administrator, syncs the governed tool provider, imports a minimal workflow DSL, exports it back into `platform/dify-workflows/`, and confirms Langfuse trace configuration can be written and read on the smoke app.

When you run the smoke flow from a linked git worktree, the script now falls back to the shared repository `.local/langfuse/` directory automatically, so trace verification still succeeds without copying controller-local secrets into the worktree.

## Operational Notes

- This workstream deploys a Dify-local Qdrant sidecar so the live apply can remain isolated from ADR 0198.
- Shared `vectors.example.com` migration should happen only after ADR 0198 is merged and applied from `main`.
- Dify remains the authoring surface. Production workflows should be exported and promoted into Windmill.
- The workstream required a one-time manual OpenBao policy upsert for `lv3-service-dify-runtime` before the repo replay could fully converge; that manual action is recorded in the live-apply receipt for this branch.
