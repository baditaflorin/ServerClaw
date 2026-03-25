# Configure Dozzle

## Purpose

This runbook converges the Dozzle hub and agent topology from ADR 0150 so
operators can use `logs.lv3.org` for real-time container logs across the Docker
guests.

## Result

- `docker-runtime-lv3` runs the Dozzle hub on `/opt/dozzle`
- `docker-runtime-lv3`, `docker-build-lv3`, and `monitoring-lv3` each run a
  Dozzle agent on port `7007`
- `logs.lv3.org` is published through the shared NGINX edge and protected by
  the repo-managed Keycloak oauth2-proxy gate
- the Dozzle hub aggregates logs from all three managed Docker guests

## Commands

Syntax-check the Dozzle workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-dozzle
```

Converge the live Dozzle hub, agents, and edge publication:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
HETZNER_DNS_API_TOKEN=... make converge-dozzle
```

## Verification

Verify the hub healthcheck on `docker-runtime-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.118.189.95 \
  ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:8089/healthcheck'
```

Verify the agents are reachable from the hub container:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.118.189.95 \
  ops@10.10.10.20 \
  'sudo docker exec dozzle /dozzle agent-test dozzle-agent:7007 && \
   sudo docker exec dozzle /dozzle agent-test 10.10.10.30:7007 && \
   sudo docker exec dozzle /dozzle agent-test 10.10.10.40:7007'
```

Verify the public hostname is OIDC-gated on the edge:

```bash
curl -Ik https://logs.lv3.org/
```

Verify the edge health endpoint responds locally on `nginx-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.118.189.95 \
  ops@10.10.10.10 \
  'curl -Ik -H "Host: logs.lv3.org" https://127.0.0.1/'
```

## Operating Notes

- Dozzle remains read-only. Container restarts and other mutations stay on the
  governed Portainer, CLI, or Windmill paths.
- The edge publication enables streaming-safe proxy settings for Server-Sent
  Events so real-time log tailing is not delayed by NGINX buffering.
- Historical search and retention remain in Loki; Dozzle is only for
  sub-second tailing and recent log context.
