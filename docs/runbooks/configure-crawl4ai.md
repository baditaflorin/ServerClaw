# Configure Crawl4AI

## Purpose

This runbook converges ADR 0288 so agents and workflows have a shared,
private Crawl4AI runtime for LLM-oriented markdown extraction from external
URLs.

## Result

- `docker-runtime-lv3` runs the stateless Crawl4AI runtime from
  `/opt/crawl4ai`
- the private runtime listens on `10.10.10.20:11235` for guest-network and
  local Docker callers
- repo-managed rate limiting, monitoring, and health settings are rendered to
  `/etc/lv3/crawl4ai/config.yml`
- verification proves the health endpoint, monitor endpoint, playground, and
  a real markdown crawl path all succeed

## Commands

Syntax-check the Crawl4AI workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-crawl4ai
```

Converge the private runtime:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-crawl4ai
```

Refresh the generated platform vars after topology or port changes:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
uv run --with pyyaml python scripts/generate_platform_vars.py --write
```

## Verification

Verify the local health endpoint on `docker-runtime-lv3`:

```bash
PROXY_COMMAND='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 -o LogLevel=ERROR -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p'
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand="$PROXY_COMMAND" \
  ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:11235/health'
```

Verify the monitoring endpoint reports an active permanent browser pool:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand="$PROXY_COMMAND" \
  ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:11235/monitor/health'
```

Verify the markdown endpoint returns cleaned content for `https://example.com/`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand="$PROXY_COMMAND" \
  ops@10.10.10.20 \
  'python3 - <<'\''PY'\''\nimport json, urllib.request\npayload = json.dumps({\"url\": \"https://example.com/\"}).encode()\nrequest = urllib.request.Request(\"http://127.0.0.1:11235/md\", data=payload, headers={\"Content-Type\": \"application/json\"})\nwith urllib.request.urlopen(request, timeout=180) as response:\n    body = json.load(response)\nassert body[\"success\"] is True\nassert \"Example Domain\" in body[\"markdown\"]\nprint(body[\"markdown\"].splitlines()[0])\nPY'
```

Verify a guest-network caller can reach the private runtime from `coolify-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand="$PROXY_COMMAND" \
  ops@10.10.10.70 \
  'curl -fsS http://10.10.10.20:11235/health'
```

## Operating Notes

- There is no public DNS record and no shared API gateway route for Crawl4AI.
  Access is intentionally limited to the private guest network and local
  Docker workloads on `docker-runtime-lv3`.
- The compose stack uses its own managed bridge network instead of Docker's
  legacy default `bridge`. Keep that isolation in place so the runtime does
  not depend on host-level default-bridge drift.
- Keep the repo-managed rate limit and crawler delay settings in
  `/etc/lv3/crawl4ai/config.yml`; do not drift them through ad hoc container
  edits.
- The mounted `/etc/lv3/crawl4ai/config.yml` fully replaces the image default.
  Keep the full upstream schema in sync when editing it, including the
  `crawler.pool`, `crawler.browser`, `redis`, and `webhooks` sections, then
  rerun `make converge-crawl4ai` so the role force-recreates the container on
  config changes.
- Use the explicit `ProxyCommand` form in this runbook instead of `-J`; the
  bootstrap key must be supplied to the Proxmox hop and plain `-J` does not
  do that in the current operator environment.
- Crawl4AI is intentionally stateless here. It returns crawl output in the
  HTTP response and does not retain crawl history as a system of record.
- This runtime is for targeted page fetches and markdown cleanup, not
  recursive full-site mirroring.
