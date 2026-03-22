# Workstream ADR 0040: Docker Runtime Container Telemetry

- ADR: [ADR 0040](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0040-docker-runtime-container-telemetry-via-telegraf-docker-input.md)
- Title: Docker runtime container telemetry
- Status: ready
- Branch: `codex/adr-0040-runtime-container-telemetry`
- Worktree: `../proxmox_florin_server-runtime-container-telemetry`
- Owner: codex
- Depends On: ADR 0011
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, `playbooks/monitoring-stack.yml`, `roles/docker_runtime_observability`, managed Grafana dashboards

## Scope

- collect Docker container metrics from `docker-runtime-lv3` through Telegraf's Docker input plugin
- ship container telemetry into the existing InfluxDB bucket on `monitoring-lv3`
- extend the managed `LV3 docker-runtime-lv3 Detail` dashboard with container-level panels and a runtime snapshot
- document the convergence and verification path for operators

## Non-Goals

- changing the Docker runtime VM software baseline from ADR 0023
- changing public publication for runtime-hosted services
- adding alert rules or notification routing for container health
- changing protected integration files such as `VERSION`, `changelog.md`, `README.md`, or `versions/stack.yaml` on the workstream branch

## Expected Repo Surfaces

- `playbooks/monitoring-stack.yml`
- `roles/docker_runtime_observability/`
- `roles/monitoring_vm/templates/_grafana_dashboard_macros.j2`
- `roles/monitoring_vm/templates/lv3-vm-detail.json.j2`
- `inventory/host_vars/proxmox_florin.yml`
- `docs/runbooks/monitoring-stack.md`
- `docs/repository-map.md`
- `docs/adr/0040-docker-runtime-container-telemetry-via-telegraf-docker-input.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-runtime-lv3` runs `telegraf` with Docker socket access
- InfluxDB receives `docker_container_*` measurements from `docker-runtime-lv3`
- `LV3 docker-runtime-lv3 Detail` shows container-level runtime data

## Verification

- `make syntax-check-monitoring`
- `ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml docker-runtime-lv3 -m shell -a 'systemctl is-active telegraf && id -nG telegraf' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> filter(fn: (r) => r.host == "docker-runtime-lv3" and (r._measurement == "docker_container_status" or r._measurement == "docker_container_cpu" or r._measurement == "docker_container_mem" or r._measurement == "docker_container_net" or r._measurement == "docker_container_health")) |> limit(n: 20)'\'''`

## Merge Criteria

- runtime telemetry convergence is idempotent
- the managed runtime detail dashboard is provisioned from repo state
- the workstream registry and this document are current
- protected integration files are reconciled only during integration on `main`

## Notes For The Next Assistant

- This workstream is ready to merge but is not live-applied yet.
- If live convergence exposes Docker socket permission issues for `telegraf`, verify the `docker` group membership and restart `telegraf` before assuming the dashboard query is wrong.
