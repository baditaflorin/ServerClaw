# Configure SearXNG

## Purpose

This runbook converges the private SearXNG runtime defined by ADR 0148 and
verifies that Open WebUI can use it for governed web search.

## Result

- `docker-runtime-lv3` runs SearXNG from `/opt/searxng`
- SearXNG listens privately on `http://10.10.10.20:8881`
- the Proxmox host publishes the operator entrypoint at `http://100.64.0.1`
- `search.lv3.org` resolves to the Proxmox host Tailscale IP for tailnet users
- the stable SearXNG secret key is mirrored under `.local/searxng/secret-key.txt`
- Open WebUI is re-rendered to use the local SearXNG JSON endpoint for web search

## Controller-Local Inputs

Generated automatically on first converge:

- `.local/searxng/secret-key.txt`

Required external input:

- `HETZNER_DNS_API_TOKEN`

## Commands

Syntax-check the SearXNG workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-searxng
```

Converge the runtime, proxy, Open WebUI integration, and tailnet DNS record:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
HETZNER_DNS_API_TOKEN=... make converge-searxng
```

## Verification

Verify the runtime containers on `docker-runtime-lv3`:

```bash
ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml docker-runtime-lv3 -m shell -a 'docker compose --file /opt/searxng/docker-compose.yml ps' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Verify the internal JSON search endpoint:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'curl -fsS "http://127.0.0.1:8881/search?q=proxmox%20ve&format=json"'
```

Verify the operator entrypoint through the Proxmox Tailscale proxy:

```bash
curl -fsS "http://100.64.0.1/search?q=proxmox%20ve&format=json"
```

Verify the tailnet hostname:

```bash
curl -fsS "http://search.lv3.org/search?q=proxmox%20ve&format=json"
```

Verify the rendered Open WebUI runtime now points at SearXNG:

```bash
ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml docker-runtime-lv3 -m shell -a "sudo grep -E '^(ENABLE_WEB_SEARCH|WEB_SEARCH_ENGINE|SEARXNG_QUERY_URL|BYPASS_WEB_SEARCH_WEB_LOADER)=' /run/lv3-secrets/open-webui/runtime.env" --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Operating Notes

- The published hostname is intentionally tailnet-only. The DNS record points to
  the Proxmox host Tailscale IP, not the public IPv4.
- The live host Tailscale IP was re-verified as `100.64.0.1` on 2026-03-25.
  Confirm `management_tailscale_ipv4` still matches the live `tailscale0`
  address before re-running the host proxy or security roles.
- Open WebUI is configured to use SearXNG search results directly and to skip
  automatic web-page loading for those search hits.
- The runtime now manages both `/etc/searxng/settings.yml` and
  `/etc/searxng/limiter.toml`. The limiter config passlists the private Docker,
  Proxmox internal, and Tailscale ranges used by Open WebUI and operators.
- If a previous converge wrote SearXNG config files without recreating the
  container, the running process can keep the old bot-detection behavior in
  memory. In that case, run `docker compose --file /opt/searxng/docker-compose.yml up -d --force-recreate --remove-orphans`
  on `docker-runtime-lv3` once, then retry the JSON verification endpoint.
- Keep `.local/searxng/` controller-only. The mirrored secret key is stable on
  purpose so browser cookies and settings survive re-converges.
