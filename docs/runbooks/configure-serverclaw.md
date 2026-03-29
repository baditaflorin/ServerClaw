# Configure ServerClaw

## Purpose

This runbook converges the first live ServerClaw surface defined by ADR 0254.

## Result

- `coolify-lv3` runs a dedicated Open WebUI-based ServerClaw runtime from `/opt/serverclaw`
- `chat.lv3.org` is published through the shared NGINX edge with in-app Keycloak OIDC enabled
- controller-local bootstrap secrets are mirrored under `.local/serverclaw/`
- the dedicated Keycloak client secret is mirrored under `.local/keycloak/serverclaw-client-secret.txt`
- the runtime uses the existing Ollama and SearXNG services on `docker-runtime-lv3`

## Controller-Local Inputs

Generated automatically on first converge:

- `.local/serverclaw/admin-password.txt`
- `.local/serverclaw/webui-secret-key.txt`
- `.local/keycloak/serverclaw-client-secret.txt`

Optional local-only input:

- `.local/serverclaw/provider.env`
  - use only for approved upstream provider overrides that must remain controller-local
  - keep `WEBUI_URL`, `OLLAMA_BASE_URL`, `SEARXNG_QUERY_URL`, auth cookies, and OIDC identity settings repo-managed

## Commands

Syntax-check the ServerClaw workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-serverclaw
```

Converge the live ServerClaw Proxmox guest firewall lane, runtime, OIDC client,
and public edge publication:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-serverclaw
```

## Verification

Verify the runtime container and generated files on `coolify-lv3`:

```bash
ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml coolify-lv3 -m shell -a 'docker compose --file /opt/serverclaw/docker-compose.yml ps && sudo ls -ld /opt/serverclaw /opt/serverclaw/data /etc/lv3/serverclaw /run/lv3-secrets/serverclaw && sudo test ! -e /opt/serverclaw/serverclaw.env' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Verify the rendered runtime env enables Keycloak, Ollama, and web search:

```bash
ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml coolify-lv3 -m shell -a "sudo grep -E '^(WEBUI_URL|WEBUI_NAME|ENABLE_OAUTH_SIGNUP|OAUTH_CLIENT_ID|OPENID_PROVIDER_URL|OLLAMA_BASE_URL|SEARXNG_QUERY_URL|DEFAULT_MODELS|DEFAULT_PINNED_MODELS)=' /run/lv3-secrets/serverclaw/runtime.env" --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Verify the Proxmox VM firewall exposes the upstream proxy lane from
`nginx-lv3` to `coolify-lv3:8096`:

```bash
ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml proxmox_florin -m shell -a "grep -n '10.10.10.10/32 -p tcp -dport 8096' /etc/pve/firewall/170.fw" --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519
```

Verify the public edge responds:

```bash
curl -I https://chat.lv3.org/
```

Verify the bootstrap admin can still sign in through the local runtime path:

```bash
ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml coolify-lv3 -m shell -a "curl -s -X POST http://127.0.0.1:8096/api/v1/auths/signin -H 'Content-Type: application/json' -d '{\"email\":\"ops@lv3.org\",\"password\":\"'\"$(sudo cat /etc/lv3/serverclaw/admin-password.txt)\"'\"}'" --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Operating Notes

- Keep `WEBUI_URL=https://chat.lv3.org` aligned with the live hostname before changing the OIDC client contract.
- Treat `.local/serverclaw/` and `.local/keycloak/serverclaw-client-secret.txt` as sensitive controller-only material.
- ServerClaw currently renders `/run/lv3-secrets/serverclaw/runtime.env` directly on `coolify-lv3` instead of running the shared OpenBao sidecar there, because the managed OpenBao automation listener remains host-local to `docker-runtime-lv3`.
- ServerClaw intentionally reuses the existing Ollama and SearXNG backends instead of standing up a separate model or search tier for ADR 0254.
- Matrix, channel bridges, delegated OpenFGA authorization, and the richer memory plane remain follow-on work for the adjacent ServerClaw ADRs.
