# Configure One-API

## Purpose

This runbook converges the private One-API LLM proxy defined by ADR 0294.

## Result

- `docker-runtime-lv3` runs One-API from `/opt/one-api`
- `postgres-lv3` stores One-API channels, tokens, quotas, and usage records in the `oneapi` database
- the Proxmox host publishes an operator-only Tailscale TCP proxy at `http://100.64.0.1:8018`
- repo-managed bootstrap logic creates the root admin contract, Ollama-backed channel aliases, and consumer tokens
- controller-local provider env files for Open WebUI and ServerClaw are generated under `.local/open-webui/provider.env` and `.local/serverclaw/provider.env`

## Controller-Local Inputs

Generated automatically on first converge:

- `.local/one-api/database-password.txt`
- `.local/one-api/session-secret.txt`
- `.local/one-api/root-access-token.txt`
- `.local/one-api/root-password.txt`
- `.local/open-webui/provider.env`
- `.local/serverclaw/provider.env`

## Commands

Syntax-check the One-API workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-one-api
```

Converge the private runtime, database, controller proxy, and bootstrap contract:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-one-api
```

## Verification

Verify the runtime container and generated files on `docker-runtime-lv3`:

```bash
ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml docker-runtime-lv3 -m shell -a 'docker compose --file /opt/one-api/docker-compose.yml ps && sudo ls -ld /opt/one-api /etc/lv3/one-api /opt/one-api/openbao /run/lv3-secrets/one-api && sudo test ! -e /opt/one-api/one-api.env' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Verify the private controller endpoint responds:

```bash
curl -fsS http://100.64.0.1:8018/api/status
```

Verify the repo-managed bootstrap contract without mutating it:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
python3 scripts/one_api_bootstrap.py verify \
  --config config/one-api/bootstrap.json \
  --one-api-url http://100.64.0.1:8018 \
  --root-access-token-file .local/one-api/root-access-token.txt \
  --write-report .local/one-api/bootstrap-report.json
```

Verify the generated provider env files still point consumers at One-API:

```bash
grep -E '^(OPENAI_API_KEY|OPENAI_API_BASE_URL)=' /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/open-webui/provider.env
grep -E '^(OPENAI_API_KEY|OPENAI_API_BASE_URL)=' /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/serverclaw/provider.env
```

## Operating Notes

- Keep One-API private-only. The supported operator path is the Proxmox host controller proxy, not a public edge route.
- Treat `.local/one-api/`, `.local/open-webui/provider.env`, and `.local/serverclaw/provider.env` as sensitive controller-only material.
- `make converge-one-api` is the authoritative replay for the unified LLM lane on this platform shape: it now converges the repo-managed Ollama dependency before One-API, then rewrites the downstream Open WebUI and ServerClaw provider env contracts from the settled bootstrap state.
- Re-run `make converge-one-api` after changing `config/one-api/bootstrap.json` or the Ollama startup model catalog so the channel and token contract stays in sync with repo truth.
- Upstream One-API does not expose a native Prometheus `/metrics` endpoint here; rely on the bootstrap verification report, service health probes, and downstream consumer checks instead of undocumented scrape assumptions.
- Open WebUI and ServerClaw should consume One-API rather than talking directly to Ollama on this platform shape.
