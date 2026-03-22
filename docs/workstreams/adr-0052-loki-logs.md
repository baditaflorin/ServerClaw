# Workstream ADR 0052: Centralized Log Aggregation With Grafana Loki

- ADR: [ADR 0052](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0052-centralized-log-aggregation-with-grafana-loki.md)
- Title: Centralized operational log search in Grafana
- Status: live_applied
- Branch: `codex/adr-0052-loki-logs`
- Worktree: `../proxmox_florin_server-loki-logs`
- Owner: codex
- Depends On: `adr-0011-monitoring`
- Conflicts With: none
- Shared Surfaces: `monitoring-lv3`, Grafana, host logs, guest logs, container logs

## Scope

- choose Loki as the central log plane
- define log collection targets, labels, and retention boundaries
- keep log search aligned with the existing monitoring surface

## Non-Goals

- replacing structured receipts with log retention

## Expected Repo Surfaces

- `Makefile`
- `playbooks/monitoring-stack.yml`
- `docs/adr/0052-centralized-log-aggregation-with-grafana-loki.md`
- `docs/workstreams/adr-0052-loki-logs.md`
- `docs/runbooks/monitoring-stack.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `roles/loki_log_agent/`
- `roles/monitoring_vm/`
- `config/workflow-catalog.json`
- `workstreams.yaml`

## Expected Live Surfaces

- Loki running on `monitoring-lv3`
- Grafana datasource `Loki Logs`
- Alloy log shipping on `proxmox_florin` and all managed guests
- governed log collection from host journald, guest journald, `nginx-lv3` NGINX files, and `docker-runtime-lv3` container logs

## Verification

- `make syntax-check-monitoring`
- `make converge-monitoring`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o 'ProxyCommand=ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p' ops@10.10.10.40 'sudo systemctl is-active grafana-server influxdb loki alloy'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o 'ProxyCommand=ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p' ops@10.10.10.40 'curl -fsS http://127.0.0.1:3100/loki/api/v1/label/host/values | jq -c .data'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o 'ProxyCommand=ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p' ops@10.10.10.40 'start=$(date -u -d "1 hour ago" +%s000000000); curl -fsSG --data-urlencode "match[]={host=\"docker-runtime-lv3\",source=\"docker\"}" --data-urlencode start=$start http://127.0.0.1:3100/loki/api/v1/series | jq -c .data'`

## Merge Criteria

- the ADR defines one central log plane and its boundaries clearly
- repo-first logging rules remain explicit

## Live Apply Notes

- Live apply completed on `2026-03-22` from `main` at repo version `0.57.0` and platform version `0.31.0`.
- `make converge-monitoring` now reruns cleanly with `ANSIBLE_HOST_KEY_CHECKING=False`, matching the existing guest-access workflows and avoiding stale guest host-key failures through the Proxmox jump path.
- Live verification confirmed Grafana datasource provisioning, Loki service health on `monitoring-lv3`, Alloy agent health on the Proxmox host and all managed guests, NGINX access-log streams for `nginx-lv3`, and Docker container-log streams for the current `docker-runtime-lv3` control-plane applications.
- A one-line `logger` event on the Proxmox host was used as deterministic verification evidence for host journald ingestion and should be treated as verification-only operational noise, not as application data.
