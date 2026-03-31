# Monitoring Stack Runbook

## Purpose

This runbook converges the dedicated monitoring VM `140` at `10.10.10.40` with:

- Grafana on port `3000`
- InfluxDB 2 on port `8086`
- Loki on loopback port `3100`
- Prometheus on loopback port `9090`
- Alertmanager on loopback port `9093`
- the Prometheus blackbox exporter on loopback port `9115`
- Loki Canary metrics on loopback port `3500`
- Tempo on loopback port `3200`
- a shared OpenTelemetry collector on private-network ports `4317` and `4318`
- a provisioned Grafana data source for the Proxmox metrics bucket
- provisioned Grafana datasources for Prometheus service-graph metrics, Tempo traces, and centralized logs
- a provisioned Grafana folder, `LV3`
- a provisioned overview dashboard, `LV3 Platform Overview`
- a provisioned runtime assurance dashboard, `LV3 Log Canary`
- a provisioned detail dashboard for each managed VM
- guest-side NGINX telemetry from `nginx-lv3`
- guest-side Docker container telemetry from `docker-runtime-lv3`
- guest-side Docker build count and duration telemetry from `docker-build-lv3`
- a Proxmox external metric server that writes into InfluxDB over the private network
- Alloy-based log shipping from the Proxmox host and all managed guests into Loki
- NGINX access and error log shipping from `nginx-lv3`
- Docker container log shipping from `docker-runtime-lv3`
- shared MinIO object storage for the Loki chunk backend after the 2026-03-30 schema cutover

Grafana is available both on the private VM and at [https://grafana.lv3.org](https://grafana.lv3.org).
The public hostname is operator-facing only: anonymous dashboard access is denied, public dashboard sharing is disabled, and the public edge now returns `404` for `/api/health` so the external surface does not disclose the running Grafana version.

## Command

```bash
make converge-monitoring
```

## Controller Prerequisites

- The shared monitoring converge path validates Alertmanager delivery into the private ntfy paging gateway and expects the controller-local secret file `.local/ntfy/alertmanager-password.txt`.
- If that file is missing in a fresh worktree, run `make converge-ntfy` first or materialize the existing controller-local secret before rerunning `make converge-monitoring`.
- The Loki chunk backend now also expects `.local/monitoring/loki-minio-secret-key.txt`; if it is missing, rerun `make converge-minio` before replaying the monitoring stack.

## What the playbook does

1. Adds the Grafana and InfluxData APT repositories on `monitoring-lv3`.
2. Installs and starts `grafana`, `influxdb2`, `influxdb2-cli`, and `loki`.
3. Installs Prometheus from Debian plus pinned `tempo` and `otelcol-contrib` Debian packages.
4. Configures a managed Prometheus service with the remote-write receiver enabled plus the `exemplar-storage` and `native-histograms` features required by Tempo span metrics and service-graph metrics.
5. Configures Alertmanager routing for severity-based notification delivery into Mattermost and the private ntfy paging gateway.
6. Configures the blackbox exporter plus generated HTTP and TCP probe jobs from `config/health-probe-catalog.json`.
7. Configures generated HTTPS and TLS assurance probes plus expiry alert rules from the service, subdomain, certificate, and health-probe catalogs.
8. Configures Tempo with local-block storage, a 7-day trace retention window, and metrics generation into Prometheus.
9. Configures the OpenTelemetry collector as the shared OTLP ingestion path for internal services and automation.
10. Initializes InfluxDB with the `lv3` organization and the `proxmox` bucket.
11. Creates separate InfluxDB tokens for Proxmox metric writes and Grafana bucket reads.
12. Provisions Grafana datasources for InfluxDB, Loki, Prometheus, and Tempo automatically.
13. Creates a dedicated guest-writer token for guest-side telemetry and mirrors it to `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/monitoring/guest-writer.token`.
14. Renders the managed dashboard JSON from repo and imports the overview plus VM detail dashboards into Grafana over the local Grafana API.
15. Creates or updates the Proxmox metric server `influxdb-http` to send metrics to `10.10.10.40:8086`.
16. Converges shared guest observability plumbing for service-level Telegraf on managed guests that ship into InfluxDB.
17. Converges `nginx-lv3` with loopback-only `stub_status` as a thin extension on top of that shared guest observability framework.
18. Converges `docker-build-lv3` with a repo-managed Docker CLI wrapper plus Telegraf shipping build count and duration events as another thin extension on the same framework.
19. Converges `docker-runtime-lv3` with Telegraf's Docker input plugin so container CPU, memory, network, status, and health data land in InfluxDB and the managed runtime detail dashboard.
20. Exposes a shared OTLP endpoint for traced internal services such as the private mail gateway.
21. Installs Grafana Alloy on `proxmox_florin` and every managed guest, labels log streams consistently, and ships host journald, guest journald, NGINX file logs, and Docker container logs into Loki.
22. Installs Loki Canary on `monitoring-lv3`, scrapes its assurance metrics in Prometheus, imports the `LV3 Log Canary` Grafana dashboard, and alerts when the log-path canary stops being writable or queryable.
23. Keeps Loki on the existing filesystem schema for pre-2026-03-30 data while writing post-cutover chunks to the shared MinIO bucket `loki-chunks`.

## Operator Access Flow

Option 1, use the published Grafana URL:

Log in at [https://grafana.lv3.org](https://grafana.lv3.org).

Option 2, use a local SSH port forward to Grafana:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 -L 3000:127.0.0.1:3000 -N
```

Retrieve the managed Grafana admin password:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'sudo cat /etc/lv3/monitoring/grafana-admin-password'
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
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'systemctl is-active influxdb grafana-server loki loki-canary alloy tempo otelcol-contrib lv3-prometheus prometheus-alertmanager prometheus-blackbox-exporter'
```

Verify the Grafana health endpoint locally on the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'curl -fsS http://127.0.0.1:3000/api/health'
```

Verify the managed overview dashboard exists and has the expected title:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'curl -fsS -u admin:$(sudo cat /etc/lv3/monitoring/grafana-admin-password) http://127.0.0.1:3000/api/dashboards/uid/lv3-platform-overview'
```

Verify unauthenticated public dashboard URLs do not expose dashboard content:

```bash
curl -I https://grafana.lv3.org/d/lv3-platform-overview/lv3-platform-overview
```

Expected result:

- `302 Found`
- `Location: /login...`

Verify the public edge blocks the Grafana health API and strips version headers:

```bash
curl -i https://grafana.lv3.org/api/health
curl -I https://grafana.lv3.org/login
```

Expected result:

- `/api/health` returns `404 Not Found`
- the response headers do not include `X-Grafana-Version` or `Via`

Verify the Grafana Loki datasource exists:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'PASS=$(sudo cat /etc/lv3/monitoring/grafana-admin-password); curl -fsS -u admin:${PASS} http://127.0.0.1:3000/api/datasources/name/Loki%20Logs | jq -r '\''[.name, .type, .url] | @tsv'\'''
```

Verify the full dashboard inventory:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'PASS=$(sudo cat /etc/lv3/monitoring/grafana-admin-password); curl -fsS -u admin:${PASS} http://127.0.0.1:3000/api/search?query=lv3 | jq -r '\''.[] | [.uid, .title, .url] | @tsv'\'''
```

Verify the managed log-canary dashboard exists:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'PASS=$(sudo cat /etc/lv3/monitoring/grafana-admin-password); curl -fsS -u admin:${PASS} http://127.0.0.1:3000/api/dashboards/uid/lv3-log-canary-overview | jq -r '\''.dashboard.title'\'''
```

Verify Loki Canary exposes metrics locally:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'curl -fsS http://127.0.0.1:3500/metrics | grep "^loki_canary_" | sed -n '\''1,20p'\'''
```

Verify Prometheus sees the Loki Canary target:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'curl -fsS --get --data-urlencode '\''query=up{job="loki-canary"}'\'' http://127.0.0.1:9090/api/v1/query | jq -c .data.result'
```

Verify Loki can still query the canary stream:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'start=$(date -u -d "15 minutes ago" +%s000000000); end=$(date -u +%s000000000); curl -fsSG --data-urlencode "query={name=\"loki-canary\",stream=\"stdout\"}" --data-urlencode limit=5 --data-urlencode start=$start --data-urlencode end=$end http://127.0.0.1:3100/loki/api/v1/query_range | jq -c .data.result'
```

Verify the shared-object-store cutover settings are present in Loki:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'sudo grep -E "object_store: s3|bucketnames: loki-chunks|delete_request_store: s3" /etc/loki/config.yml'
```

If the canary raises alerts or one of these checks fails, continue in [docs/runbooks/log-queryability-canary.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/log-queryability-canary.md).

Verify Loki currently knows about every managed host label:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'curl -fsS http://127.0.0.1:3100/loki/api/v1/label/host/values | jq -c .data'
```

Verify Docker container log streams are present in Loki:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'start=$(date -u -d "1 hour ago" +%s000000000); curl -fsSG --data-urlencode "match[]={host=\"docker-runtime-lv3\",source=\"docker\"}" --data-urlencode start=$start http://127.0.0.1:3100/loki/api/v1/series | jq -c .data'
```

Verify NGINX access logs are present in Loki:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'start=$(date -u -d "1 hour ago" +%s000000000); curl -fsSG --data-urlencode "match[]={host=\"nginx-lv3\",service=\"nginx\",log_type=\"access\"}" --data-urlencode start=$start http://127.0.0.1:3100/loki/api/v1/series | jq -c .data'
```

If you need deterministic proof for Proxmox-host journald ingestion, emit one verification-only syslog line on the host and query it from Loki:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo logger -t adr0052-verification "proxmox host loki verification event"'
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'start=$(date -u -d "10 minutes ago" +%s000000000); end=$(date -u +%s000000000); curl -fsSG --data-urlencode "query={host=\"proxmox_florin\",syslog_identifier=\"adr0052-verification\"}" --data-urlencode limit=5 --data-urlencode start=$start --data-urlencode end=$end http://127.0.0.1:3100/loki/api/v1/query_range | jq -c .data.result'
```

Verify Tempo has recorded service names from traced workloads:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'curl -fsS http://127.0.0.1:3200/api/search/tag/service.name/values'
```

Verify Tempo service-graph metrics are present in Prometheus:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'curl -fsS --get --data-urlencode '\''query=traces_service_graph_request_total'\'' http://127.0.0.1:9090/api/v1/query'
```

Verify Tempo span metrics are present in Prometheus:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'curl -fsS --get --data-urlencode '\''query=traces_spanmetrics_calls_total'\'' http://127.0.0.1:9090/api/v1/query'
```

Verify Alertmanager is healthy:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'curl -fsS http://127.0.0.1:9093/-/healthy'
```

Verify the blackbox exporter is healthy:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'curl -fsS http://127.0.0.1:9115/-/healthy'
```

Verify nginx guest telemetry is present in InfluxDB:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> filter(fn: (r) => r._measurement == "nginx" and r.host == "nginx-lv3") |> limit(n: 10)'\'''
```

Verify docker build count and duration telemetry is present in InfluxDB:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> filter(fn: (r) => r._measurement == "docker_builds" and r.host == "docker-build-lv3" and (r._field == "count" or r._field == "duration_ms" or r._field == "start_time_ns" or r._field == "end_time_ns")) |> limit(n: 20)'\'''
```

Verify docker runtime container telemetry is present in InfluxDB:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> filter(fn: (r) => r.host == "docker-runtime-lv3" and (r._measurement == "docker_container_status" or r._measurement == "docker_container_cpu" or r._measurement == "docker_container_mem" or r._measurement == "docker_container_net" or r._measurement == "docker_container_health")) |> limit(n: 20)'\'''
```

Verify Telegraf has Docker socket access on the runtime guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'systemctl is-active telegraf && id -nG telegraf'
```

Verify local nginx `stub_status` on the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.10 'curl -fsS http://127.0.0.1:8080/basic_status'
```

Verify the Docker wrapper and Telegraf on the build guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.30 'bash -lc "command -v docker" && systemctl is-active telegraf'
```

Verify the Proxmox metric server definition on the host:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo pvesh get /cluster/metrics/server/influxdb-http --output-format json'
```

Verify that recent Proxmox metrics are arriving in InfluxDB:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> limit(n: 5)'\'''
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
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/monitoring/loki-minio-secret-key.txt`

The shared trace ingress for instrumented private services is:

- OTLP gRPC: `10.10.10.40:4317`
- OTLP HTTP: `http://10.10.10.40:4318/v1/traces`

If the mirrored local token is missing, rerun `make converge-monitoring` from the control machine.

## Recovery Note

During the live rollout on 2026-03-22, VMs `110`, `120`, `130`, and `140` again had stale netplan MAC metadata and the Proxmox host returned `Destination Host Unreachable` for the private guest IPs.

The repair used the existing guest-agent flow from the netplan drift runbook before rerunning the monitoring playbook:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo qm config 110 | grep ^net0 && sudo qm config 120 | grep ^net0 && sudo qm config 130 | grep ^net0 && sudo qm config 140 | grep ^net0'
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 "sudo qm guest exec 110 -- bash -lc 'sed -i \"s/bc:24:11:94:37:83/bc:24:11:0d:03:bb/\" /etc/netplan/50-cloud-init.yaml && netplan apply'"
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 "sudo qm guest exec 120 -- bash -lc 'sed -i \"s/bc:24:11:b0:d4:d1/bc:24:11:aa:99:7c/\" /etc/netplan/50-cloud-init.yaml && netplan apply'"
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 "sudo qm guest exec 130 -- bash -lc 'sed -i \"s/bc:24:11:7c:4e:5b/bc:24:11:0f:8a:f2/\" /etc/netplan/50-cloud-init.yaml && netplan apply'"
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 "sudo qm guest exec 140 -- bash -lc 'sed -i \"s/bc:24:11:82:c6:38/bc:24:11:b1:76:a0/\" /etc/netplan/50-cloud-init.yaml && netplan apply'"
```
