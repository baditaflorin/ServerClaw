# Workstream ADR 0027: Uptime Kuma On The Docker Runtime VM

- ADR: [ADR 0027](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0027-uptime-kuma-on-the-docker-runtime-vm.md)
- Title: Uptime Kuma rollout on the Docker runtime VM
- Status: merged
- Branch: `codex/adr-0022-uptime-kuma`
- Worktree: `../proxmox_florin_server-uptime-kuma`
- Owner: codex
- Depends On: ADR 0014, ADR 0021
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, `uptime.lv3.org`, `/opt/uptime-kuma`, NGINX edge publication, Hetzner DNS zone `lv3.org`

## Scope

- deploy Uptime Kuma on `docker-runtime-lv3` under `/opt/uptime-kuma`
- publish `uptime.lv3.org` through Hetzner DNS and the NGINX edge
- make the edge certificate automation expand when a new hostname is added
- seed the first managed monitor set
- add a repo-local client flow for future monitor management from the control machine

## Non-Goals

- replacing the Grafana or InfluxDB monitoring stack
- introducing notification-provider secrets for paging or chat integrations
- exposing the Docker runtime VM directly to the public internet
- changing protected integration files such as `VERSION`, `changelog.md`, `README.md`, or `versions/stack.yaml` on the workstream branch

## Expected Repo Surfaces

- `playbooks/uptime-kuma.yml`
- `roles/uptime_kuma_runtime/`
- `roles/hetzner_dns_records/`
- `roles/nginx_edge_publication/`
- `inventory/group_vars/all.yml`
- `config/uptime-kuma/monitors.json`
- `scripts/uptime_kuma_tool.py`
- `docs/runbooks/deploy-uptime-kuma.md`
- `docs/adr/0027-uptime-kuma-on-the-docker-runtime-vm.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-runtime-lv3` listens on TCP `3001` for the Uptime Kuma container
- `/opt/uptime-kuma` exists with persistent application data under `/opt/uptime-kuma/data`
- `uptime.lv3.org` exists in Hetzner DNS
- the NGINX edge reverse proxies `https://uptime.lv3.org`
- the Uptime Kuma instance has a durable local auth path and an initial managed monitor set

## Verification

- `make syntax-check-uptime-kuma`
- `HETZNER_DNS_API_TOKEN=... make deploy-uptime-kuma`
- `ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml docker-runtime-lv3 -m shell -a 'sudo docker ps --filter name=uptime-kuma' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
- `curl -I https://uptime.lv3.org`
- `python3 /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/uptime_kuma_tool.py list-monitors`

## Merge Criteria

- deployment automation is idempotent for DNS, runtime, and edge publication
- the workstream registry and this document are current
- the first monitor seed is reproducible from repo state
- protected integration files are reconciled only during integration on `main`

## Notes For The Next Assistant

- Uptime Kuma monitor management relies on the internal Socket.IO management flow because the official API key support is limited to metrics endpoints.
- Keep local auth material under `.local/uptime-kuma/` and out of git.
- Live apply succeeded on `2026-03-22`.
- During integration this workstream was renumbered to ADR 0027 because ADR 0022 was already assigned on `main`.
- During live apply, all four initial guests (`110/120/130/140`) were found with stale netplan MAC matches and had to be repaired in place through the QEMU guest agent before private-network reachability returned.
- The repair procedure is documented in `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/repair-guest-netplan-mac-drift.md`.
