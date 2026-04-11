# Configure Netdata

## Purpose

This runbook converges the ADR 0196 Netdata parent and child streaming topology
and verifies both the private monitoring surface and the authenticated public
edge route at `realtime.example.com`.

## Result

- `monitoring` runs the Netdata parent on port `19999`
- `proxmox-host`, `nginx-edge`, `docker-runtime`, and `postgres`
  stream into the monitoring parent
- Prometheus scrapes the consolidated Netdata exporter from `monitoring`
- `realtime.example.com` is published on the shared NGINX edge behind the
  repo-managed Keycloak oauth2-proxy gate

## Commands

Syntax-check the realtime playbook through the governed make target:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
make syntax-check-realtime
```

Provision the public DNS record:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
HETZNER_DNS_API_TOKEN=... make provision-subdomain FQDN=realtime.example.com
```

Apply the realtime service from the governed generic service entrypoint:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
make live-apply-service service=realtime env=production EXTRA_ARGS='-e bypass_promotion=true'
```

Replay the dedicated realtime workflow wrapper when you want the explicit
workflow-catalog contract instead of the generic service entrypoint:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
HETZNER_DNS_API_TOKEN=... \
BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
make converge-realtime env=production
```

Bootstrap or refresh the generated Uptime Kuma monitor set after changing the
health-probe catalog:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
make uptime-kuma-manage ACTION=bootstrap UPTIME_KUMA_ARGS='--base-url https://uptime.example.com'
make uptime-kuma-manage ACTION=ensure-monitors
```

## Verification

Verify the private Netdata parent endpoint on `monitoring`:

```bash
KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519
ssh -i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p" \
  ops@10.10.10.40 'curl -fsS http://127.0.0.1:19999/api/v1/info'
```

Verify consolidated metrics for the streamed nodes are present on the parent:

```bash
KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519
ssh -i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p" \
  ops@10.10.10.40 'curl -fsS "http://127.0.0.1:19999/api/v1/allmetrics?format=prometheus_all_hosts&source=as-collected" | grep -E "host=\\\"(proxmox-host|nginx-edge|docker-runtime|postgres|monitoring)\\\"" | head'
```

Verify the Prometheus scrape path now sees Netdata metrics:

```bash
KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519
ssh -i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p" \
  ops@10.10.10.40 'curl -fsS --get --data-urlencode '\''query=netdata_info{job="netdata"}'\'' http://127.0.0.1:9090/api/v1/query'
```

Verify the public hostname is published in DNS and routed through the shared
authenticated edge:

```bash
dig +short realtime.example.com
curl -Ik https://realtime.example.com/
```

Verify the private Uptime Kuma monitor exists:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
make uptime-kuma-manage ACTION=list-monitors
```

## Operating Notes

- Netdata is intentionally the live troubleshooting surface, not the
  long-retention metrics system of record.
- The realtime playbook now builds the generated docs and changelog portals on
  the controller before edge publication, so fresh parallel worktrees do not
  need a manual portal pre-build step.
- On Debian 13 guests, the Netdata role bootstraps the official Netdata apt
  repository automatically when the distro repositories do not yet publish a
  `netdata` package candidate.
- `make uptime-kuma-manage` now defaults its durable auth file to the primary
  checkout's `.local/uptime-kuma/admin-session.json`, so separate worktrees can
  reuse the existing Uptime Kuma session without copying local secrets.
- Keep `realtime.example.com` on the shared authenticated edge; do not weaken the
  publication model with anonymous public access.
- The parent retains only short-lived data so longer-range investigations
  should move into Grafana and Prometheus after the incident is stabilized.
