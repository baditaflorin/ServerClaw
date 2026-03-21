# Workstream ADR 0011: Monitoring Stack Rollout

- ADR: [ADR 0011](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0011-monitoring-vm-with-grafana-and-proxmox-metrics.md)
- Title: Monitoring VM and Grafana rollout
- Status: merged
- Branch: `codex/adr-0011-monitoring`
- Worktree: `../proxmox_florin_server-monitoring`
- Owner: codex
- Depends On: none
- Conflicts With: none
- Shared Surfaces: `monitoring-lv3`, `grafana.lv3.org`, Proxmox metrics export

## Scope

- converge the monitoring VM at `10.10.10.40`
- install Grafana and the chosen metric store
- wire Proxmox host metrics into the monitoring stack
- document the operator access path and verification flow

## Non-Goals

- Tailscale rollout
- backup policy
- replacing the current ingress model
- public Grafana publication before the private access model settles

## Expected Repo Surfaces

- `playbooks/monitoring-stack.yml`
- `roles/monitoring_vm/`
- `roles/proxmox_metrics/`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/all.yml`
- `Makefile`
- `docs/runbooks/`
- `docs/adr/0011-monitoring-vm-with-grafana-and-proxmox-metrics.md`

## Expected Live Surfaces

- VM `140`
- Proxmox metric export configuration

## Verification

```bash
make syntax-check-monitoring
```

```bash
make converge-monitoring
```

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@65.108.75.123 ops@10.10.10.40 'systemctl is-active influxdb grafana-server && sudo ls -l /etc/lv3/monitoring'
```

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@65.108.75.123 'sudo pvesh get /cluster/metrics/server/influxdb-http --output-format json'
```

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@65.108.75.123 ops@10.10.10.40 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> limit(n: 5)'\'''
```

## Merge Criteria

- automation is idempotent
- provisioning steps and operator flow are documented
- workstream status is updated in `workstreams.yaml`
- branch syntax checks pass

## Notes For The Next Assistant

- keep monitoring isolated from Tailscale changes unless there is an explicit dependency
- do not update `platform_version` until the merged work is actually applied live from `main`
- Grafana stays internal-only in this workstream; use SSH port-forwarding until private access and publication are merged separately
- this workstream is merged to `main` but not yet applied live
