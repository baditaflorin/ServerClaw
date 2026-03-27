# Deploy Uptime Kuma

## Purpose

This runbook converges Uptime Kuma on the Docker runtime VM and publishes it through the NGINX edge at `https://uptime.lv3.org`.

## Result

- Hetzner DNS contains the `uptime.lv3.org` A record
- `docker-runtime-lv3` runs Uptime Kuma from `/opt/uptime-kuma`
- `nginx-lv3` reverse proxies `uptime.lv3.org` and expands the shared edge certificate when needed
- local control-machine auth for future monitor management is stored under `.local/uptime-kuma/`
- the first repo-managed monitor set is applied from generated `config/uptime-kuma/monitors.json`
- the public status-page definition is reconciled from `config/uptime-kuma/status-page.json`

## Commands

Deploy the runtime, DNS record, and NGINX publication:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
HETZNER_DNS_API_TOKEN=... make deploy-uptime-kuma
```

Prepare a small local client environment for repo-driven monitor management:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
python3 -m venv .local/uptime-kuma/client-venv
.local/uptime-kuma/client-venv/bin/pip install -r requirements/uptime-kuma-client.txt
```

Bootstrap the first durable local auth file and seed the initial monitors:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make uptime-kuma-manage ACTION=bootstrap UPTIME_KUMA_ARGS="--base-url https://uptime.lv3.org"
```

Re-apply the repo-managed monitor seed later:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
python3 scripts/uptime_contract.py --write
make uptime-kuma-manage ACTION=ensure-monitors
```

Reconcile the repo-managed public status page:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make uptime-kuma-manage ACTION=ensure-status-page
```

List the current monitors from the repo client:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make uptime-kuma-manage ACTION=list-monitors
```

List the current maintenances from the repo client:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make uptime-kuma-manage ACTION=list-maintenances
```

## Verification

Verify the runtime container:

```bash
ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml docker-runtime-lv3 -m shell -a 'sudo docker ps --filter name=uptime-kuma && sudo ls -ld /opt/uptime-kuma /opt/uptime-kuma/data' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Verify public publication:

```bash
curl -I https://uptime.lv3.org
curl -I https://nginx.lv3.org
```

Verify the seeded monitors are visible:

```bash
make uptime-kuma-manage ACTION=list-monitors
```

Verify the status-page definition can be reconciled:

```bash
make uptime-kuma-manage ACTION=ensure-status-page
curl -I https://status.lv3.org
```

## Notes

- Uptime Kuma's built-in API key support is useful for metrics endpoints, but monitor management still uses the internal Socket.IO application flow. The repo client script is built around that supported behavior.
- Keep `.local/uptime-kuma/` local-only. It contains the durable auth material needed for future repo-driven monitor changes.
- Do not hand-edit `config/uptime-kuma/monitors.json`; regenerate it from `config/health-probe-catalog.json`.
- The NGINX role in this repo now expands the shared `lv3-edge` certificate when a new published hostname is added, so future edge applications should use the same publication path.
- The public status page runbook lives in `docs/runbooks/public-status-page.md` and covers the independent Uptime Robot monitor contract alongside the Uptime Kuma definition.
