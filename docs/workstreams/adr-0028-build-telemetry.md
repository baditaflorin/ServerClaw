# Workstream ADR 0028: Docker Build VM Build Telemetry

- ADR: [ADR 0028](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0028-docker-build-vm-build-count-telemetry-via-cli-wrapper-events.md)
- Title: Docker build VM build telemetry
- Status: live_applied
- Branch: `codex/adr-0028-build-telemetry`
- Worktree: `../proxmox_florin_server-build-telemetry`
- Owner: codex
- Depends On: ADR 0011
- Conflicts With: none
- Shared Surfaces: `docker-build-lv3`, `playbooks/monitoring-stack.yml`, `roles/docker_build_observability`, managed Grafana dashboards

## Scope

- install a repo-managed Docker CLI wrapper on `docker-build-lv3`
- receive local build events with Telegraf on the build VM
- ship the resulting `docker_builds` measurement into the existing InfluxDB bucket on `monitoring-lv3`
- add managed Grafana panels that answer how many builds were started
- document the operator convergence and verification path

## Non-Goals

- changing the Docker runtime VM baseline
- introducing CI system telemetry or per-repository build accounting
- exposing the build VM or local event listener publicly
- changing protected integration files such as `VERSION`, `changelog.md`, `README.md`, or `versions/stack.yaml` on the workstream branch

## Expected Repo Surfaces

- `playbooks/monitoring-stack.yml`
- `roles/docker_build_observability/`
- `roles/monitoring_vm/templates/_grafana_dashboard_macros.j2`
- `roles/monitoring_vm/templates/lv3-platform-overview.json.j2`
- `roles/monitoring_vm/templates/lv3-vm-detail.json.j2`
- `inventory/group_vars/all.yml`
- `docs/runbooks/monitoring-stack.md`
- `docs/runbooks/repair-guest-netplan-mac-drift.md`
- `docs/adr/0028-docker-build-vm-build-count-telemetry-via-cli-wrapper-events.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-build-lv3` records build events through `/usr/local/bin/docker`
- `telegraf` runs on `docker-build-lv3`
- InfluxDB receives `docker_builds` events from the build VM
- Grafana dashboards show build-count panels for the build VM

## Verification

- `make syntax-check-monitoring`
- `make converge-monitoring`
- `ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml docker-build-lv3 -m shell -a 'bash -lc "command -v docker && systemctl is-active telegraf"' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> filter(fn: (r) => r._measurement == "docker_builds" and r.host == "docker-build-lv3") |> limit(n: 5)'\'''`

## Merge Criteria

- build telemetry convergence is idempotent
- Grafana panels are provisioned from repo state
- the workstream registry and this document are current
- protected integration files are reconciled only during integration on `main`

## Notes For The Next Assistant

- Live apply on `2026-03-22` required another guest-agent netplan MAC repair on VMs `110`, `120`, `130`, and `140` before the SSH jump path returned; the repair flow is documented in [/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/repair-guest-netplan-mac-drift.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/repair-guest-netplan-mac-drift.md).
- This work intentionally tracks build counts, not per-project build metadata.
