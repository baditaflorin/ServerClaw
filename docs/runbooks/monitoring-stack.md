# Monitoring Stack Runbook

## Purpose

This runbook converges the dedicated monitoring VM `140` at `10.10.10.40` with:

- Grafana on port `3000`
- InfluxDB 2 on port `8086`
- Prometheus on loopback port `9090`
- Tempo on loopback port `3200`
- a shared OpenTelemetry collector on private-network ports `4317` and `4318`
- a provisioned Grafana data source for the Proxmox metrics bucket
- provisioned Grafana datasources for Prometheus service-graph metrics and Tempo traces
- a provisioned Grafana folder, `LV3`
- a provisioned overview dashboard, `LV3 Platform Overview`
- a provisioned detail dashboard for each managed VM
- guest-side NGINX telemetry from `nginx-lv3`
- guest-side Docker container telemetry from `docker-runtime-lv3`
- guest-side Docker build count and duration telemetry from `docker-build-lv3`
- a Proxmox external metric server that writes into InfluxDB over the private network

Grafana is available both on the private VM and at [https://grafana.lv3.org](https://grafana.lv3.org).

## Command

```bash
make converge-monitoring
```

## What the playbook does

1. Adds the Grafana and InfluxData APT repositories on `monitoring-lv3`.
2. Installs and starts `grafana`, `influxdb2`, and `influxdb2-cli`.
3. Installs Prometheus from Debian plus pinned `tempo` and `otelcol-contrib` Debian packages.
4. Configures a managed Prometheus service with the remote-write receiver enabled plus the `exemplar-storage` and `native-histograms` features required by Tempo span metrics and service-graph metrics.
5. Configures Tempo with local-block storage, a 7-day trace retention window, and metrics generation into Prometheus.
6. Configures the OpenTelemetry collector as the shared OTLP ingestion path for internal services and automation.
7. Initializes InfluxDB with the `lv3` organization and the `proxmox` bucket.
8. Creates separate InfluxDB tokens for Proxmox metric writes and Grafana bucket reads.
9. Provisions Grafana datasources for InfluxDB, Prometheus, and Tempo automatically.
10. Creates a dedicated guest-writer token for guest-side telemetry and mirrors it to `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/monitoring/guest-writer.token`.
11. Renders the managed dashboard JSON from repo and imports the overview plus VM detail dashboards into Grafana over the local Grafana API.
12. Creates or updates the Proxmox metric server `influxdb-http` to send metrics to `10.10.10.40:8086`.
13. Converges shared guest observability plumbing for service-level Telegraf on managed guests that ship into InfluxDB.
14. Converges `nginx-lv3` with loopback-only `stub_status` as a thin extension on top of that shared guest observability framework.
15. Converges `docker-build-lv3` with a repo-managed Docker CLI wrapper plus Telegraf shipping build count and duration events as another thin extension on the same framework.
16. Converges `docker-runtime-lv3` with Telegraf's Docker input plugin so container CPU, memory, network, status, and health data land in InfluxDB and the managed runtime detail dashboard.
17. Exposes a shared OTLP endpoint for traced internal services such as the private mail gateway.

## Operator Access Flow

Option 1, use the published Grafana URL:

Log in at [https://grafana.lv3.org](https://grafana.lv3.org).

Option 2, use a local SSH port forward to Grafana:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 -L 3000:127.0.0.1:3000 -N
```

Retrieve the managed Grafana admin password:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'sudo cat /etc/lv3/monitoring/grafana-admin-password'
```

Then log in at [http://127.0.0.1:3000](http://127.0.0.1:3000) with:

- username: `admin`
- password: the retrieved secret

## Verification

Syntax-check the dedicated monitoring playbook:

```bash
make syntax-check-monitoring
```

Verify the monitoring services on VM `140`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'systemctl is-active influxdb grafana-server tempo otelcol-contrib lv3-prometheus'
```

Verify the Grafana health endpoint locally on the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'curl -fsS http://127.0.0.1:3000/api/health'
```

Verify the managed overview dashboard exists and has the expected title:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'curl -fsS -u admin:$(sudo cat /etc/lv3/monitoring/grafana-admin-password) http://127.0.0.1:3000/api/dashboards/uid/lv3-platform-overview'
```

Verify the full dashboard inventory:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'PASS=$(sudo cat /etc/lv3/monitoring/grafana-admin-password); curl -fsS -u admin:${PASS} http://127.0.0.1:3000/api/search?query=lv3 | jq -r '\''.[] | [.uid, .title, .url] | @tsv'\'''
```

Verify Tempo has recorded service names from traced workloads:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'curl -fsS http://127.0.0.1:3200/api/search/tag/service.name/values'
```

Verify Tempo service-graph metrics are present in Prometheus:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'curl -fsS --get --data-urlencode '\''query=traces_service_graph_request_total'\'' http://127.0.0.1:9090/api/v1/query'
```

Verify Tempo span metrics are present in Prometheus:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'curl -fsS --get --data-urlencode '\''query=traces_spanmetrics_calls_total'\'' http://127.0.0.1:9090/api/v1/query'
```

Verify nginx guest telemetry is present in InfluxDB:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> filter(fn: (r) => r._measurement == "nginx" and r.host == "nginx-lv3") |> limit(n: 10)'\'''
```

Verify docker build count and duration telemetry is present in InfluxDB:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> filter(fn: (r) => r._measurement == "docker_builds" and r.host == "docker-build-lv3" and (r._field == "count" or r._field == "duration_ms" or r._field == "start_time_ns" or r._field == "end_time_ns")) |> limit(n: 20)'\'''
```

Verify docker runtime container telemetry is present in InfluxDB:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> filter(fn: (r) => r.host == "docker-runtime-lv3" and (r._measurement == "docker_container_status" or r._measurement == "docker_container_cpu" or r._measurement == "docker_container_mem" or r._measurement == "docker_container_net" or r._measurement == "docker_container_health")) |> limit(n: 20)'\'''
```

Verify Telegraf has Docker socket access on the runtime guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'systemctl is-active telegraf && id -nG telegraf'
```

Verify local nginx `stub_status` on the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.10 'curl -fsS http://127.0.0.1:8080/basic_status'
```

Verify the Docker wrapper and Telegraf on the build guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.30 'bash -lc "command -v docker" && systemctl is-active telegraf'
```

Verify the Proxmox metric server definition on the host:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo pvesh get /cluster/metrics/server/influxdb-http --output-format json'
```

Verify that recent Proxmox metrics are arriving in InfluxDB:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> limit(n: 5)'\'''
```

## Managed Secrets

The playbook keeps these secrets on the monitoring VM:

- `/etc/lv3/monitoring/grafana-admin-password`
- `/etc/lv3/monitoring/influxdb-admin-password`
- `/etc/lv3/monitoring/influxdb-operator.token`
- `/etc/lv3/monitoring/influxdb-proxmox-writer.token`
- `/etc/lv3/monitoring/influxdb-guest-writer.token`
- `/etc/lv3/monitoring/grafana-reader.token`

The control machine keeps one mirrored token outside git for host-side Proxmox configuration:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/monitoring/proxmox-writer.token`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/monitoring/guest-writer.token`

The shared trace ingress for instrumented private services is:

- OTLP gRPC: `10.10.10.40:4317`
- OTLP HTTP: `http://10.10.10.40:4318/v1/traces`

If the mirrored local token is missing, rerun `make converge-monitoring` from the control machine.

## Recovery Note

During the live rollout on 2026-03-22, VMs `110`, `120`, `130`, and `140` again had stale netplan MAC metadata and the Proxmox host returned `Destination Host Unreachable` for the private guest IPs.

The repair used the existing guest-agent flow from the netplan drift runbook before rerunning the monitoring playbook:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo qm config 110 | grep ^net0 && sudo qm config 120 | grep ^net0 && sudo qm config 130 | grep ^net0 && sudo qm config 140 | grep ^net0'
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 "sudo qm guest exec 110 -- bash -lc 'sed -i \"s/bc:24:11:94:37:83/bc:24:11:0d:03:bb/\" /etc/netplan/50-cloud-init.yaml && netplan apply'"
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 "sudo qm guest exec 120 -- bash -lc 'sed -i \"s/bc:24:11:b0:d4:d1/bc:24:11:aa:99:7c/\" /etc/netplan/50-cloud-init.yaml && netplan apply'"
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 "sudo qm guest exec 130 -- bash -lc 'sed -i \"s/bc:24:11:7c:4e:5b/bc:24:11:0f:8a:f2/\" /etc/netplan/50-cloud-init.yaml && netplan apply'"
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 "sudo qm guest exec 140 -- bash -lc 'sed -i \"s/bc:24:11:82:c6:38/bc:24:11:b1:76:a0/\" /etc/netplan/50-cloud-init.yaml && netplan apply'"
```
