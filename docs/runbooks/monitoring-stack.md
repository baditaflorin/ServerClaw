# Monitoring Stack Runbook

## Purpose

This runbook converges the dedicated monitoring VM from the current private inventory with:

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
- guest-side NGINX telemetry from `nginx-edge`
- guest-side Docker container telemetry from `docker-runtime`
- guest-side Docker build count and duration telemetry from `docker-build`
- a Proxmox external metric server that writes into InfluxDB over the private network
- Alloy-based log shipping from the Proxmox host and all managed guests into Loki
- NGINX access and error log shipping from `nginx-edge`
- Docker container log shipping from `docker-runtime`
- shared MinIO object storage for the Loki chunk backend after the 2026-03-30 schema cutover

Grafana is intended to be available on the monitoring VM and through the configured public service URL. Verify the live route before relying on either path.

> **Connection drift:** older copies of this runbook used `10.10.10.40` and the `100.64.0.1` jump host. Those no longer match the current private inventory. Use the current generated inventory and its local SSH alias for the monitoring guest. Other legacy cross-guest examples below must also be checked against inventory before use.
The public hostname is operator-facing only: anonymous dashboard access is denied, public dashboard sharing is disabled, and the public edge now returns `404` for `/api/health` so the external surface does not disclose the running Grafana version.

## Command

```bash
make converge-monitoring
```

To apply only the managed build-trial dashboard after the monitoring role change
has merged, use the scoped Grafana playbook and the `build_trial_dashboard` tag:

```bash
LOCAL_OVERLAY_ROOT="$(scripts/resolve_local_overlay_root.sh)"
DEPLOYMENT_ID="<deployment>"
IDENTITY_OVERLAY="$LOCAL_OVERLAY_ROOT/deployments/$DEPLOYMENT_ID/identity.yml"
CONNECTION_OVERLAY="$LOCAL_OVERLAY_ROOT/deployments/$DEPLOYMENT_ID/ansible-connection.yml"

PLATFORM_IDENTITY_OVERLAY="$IDENTITY_OVERLAY" \
PLATFORM_INVENTORY_OVERLAY="$CONNECTION_OVERLAY" \
uv run --with pyyaml python3 scripts/ansible_scope_runner.py plan \
  --inventory inventory/hosts.yml \
  --inventory "$CONNECTION_OVERLAY" \
  --playbook playbooks/services/grafana.yml \
  --env production

PLATFORM_IDENTITY_OVERLAY="$IDENTITY_OVERLAY" \
PLATFORM_INVENTORY_OVERLAY="$CONNECTION_OVERLAY" \
uv run --with pyyaml python3 scripts/ansible_scope_runner.py run \
  --inventory inventory/hosts.yml \
  --inventory "$CONNECTION_OVERLAY" \
  --playbook playbooks/services/grafana.yml \
  --env production -- \
  --limit monitoring \
  --tags build_trial_dashboard
```

The connection overlay must route `monitoring` through the selected deployment's
operator SSH alias when the controller cannot reach its private address
directly. Keep that mapping in the private deployment overlay; do not pass an
`ansible_host` extra-var, because the scope runner rejects connection-identity
overrides when a deployment identity is selected. The narrow tag loads the
Grafana admin credential, copies and imports the dashboard, then verifies its
Grafana UID. It does not run the public-edge checks; use the full monitoring
convergence after the public Grafana route is healthy.

## Controller Prerequisites

- The shared monitoring converge path validates Alertmanager delivery into the governed ntfy push channel and expects the controller-local secret file `.local/ntfy/alertmanager-password.txt`.
- If that file is missing in a fresh worktree, run `make converge-ntfy` first or materialize the existing controller-local secret before rerunning `make converge-monitoring`.
- The Loki chunk backend now also expects `.local/monitoring/loki-minio-secret-key.txt`; if it is missing, rerun `make converge-minio` before replaying the monitoring stack.

## What the playbook does

1. Adds the Grafana and InfluxData APT repositories on `monitoring`.
2. Installs and starts `grafana`, `influxdb2`, `influxdb2-cli`, and `loki`.
3. Installs Prometheus from Debian plus pinned `tempo` and `otelcol-contrib` Debian packages.
4. Configures a managed Prometheus service with the remote-write receiver enabled plus the `exemplar-storage` and `native-histograms` features required by Tempo span metrics and service-graph metrics.
5. Configures Alertmanager routing for severity-based notification delivery into Mattermost and the governed ntfy push channel.
6. Configures the blackbox exporter plus generated HTTP and TCP probe jobs from `config/health-probe-catalog.json`.
7. Configures generated HTTPS and TLS assurance probes plus expiry alert rules from the service, subdomain, certificate, and health-probe catalogs.
8. Configures Tempo with local-block storage, a 7-day trace retention window, and metrics generation into Prometheus.
9. Configures the OpenTelemetry collector as the shared OTLP ingestion path for internal services and automation.
10. Initializes InfluxDB with the `lv3` organization and the `proxmox` bucket.
11. Creates separate InfluxDB tokens for Proxmox metric writes and Grafana bucket reads.
12. Provisions Grafana datasources for InfluxDB, Loki, Prometheus, and Tempo automatically.
13. Creates a dedicated guest-writer token for guest-side telemetry and mirrors it to `.local/monitoring/guest-writer.token`.
14. Renders the managed dashboard JSON from repo and imports the overview plus VM detail dashboards into Grafana over the local Grafana API.
15. Creates or updates the Proxmox metric server `influxdb-http` to send metrics to the inventory-resolved monitoring address on port `8086`.
16. Converges shared guest observability plumbing for service-level Telegraf on managed guests that ship into InfluxDB.
17. Converges `nginx-edge` with loopback-only `stub_status` as a thin extension on top of that shared guest observability framework.
18. Converges `docker-build` with a repo-managed Docker CLI wrapper plus Telegraf shipping build count and duration events as another thin extension on the same framework.
19. Converges `docker-runtime` with Telegraf's Docker input plugin so container CPU, memory, network, status, and health data land in InfluxDB and the managed runtime detail dashboard.
20. Exposes a shared OTLP endpoint for traced internal services such as the private mail gateway.
21. Installs Grafana Alloy on `proxmox-host` and every managed guest, labels log streams consistently, and ships host journald, guest journald, NGINX file logs, and Docker container logs into Loki.
22. Installs Loki Canary on `monitoring`, scrapes its assurance metrics in Prometheus, imports the `LV3 Log Canary` Grafana dashboard, and alerts when the log-path canary stops being writable or queryable.
23. Keeps Loki on the existing filesystem schema for pre-2026-03-30 data while writing post-cutover chunks to the shared MinIO bucket `loki-chunks`.

## Operator Access Flow

Option 1, use the published Grafana URL:

Log in at the configured public Grafana URL after verifying that its health check succeeds.

Option 2, use a local SSH port forward to Grafana. Set `MONITORING_SSH_ALIAS` to the monitoring target in the generated private SSH configuration first:

```bash
ssh "$MONITORING_SSH_ALIAS" -L 3000:127.0.0.1:3000 -N
```

Use the approved Grafana credential flow for the admin account. Do not put the
password on a command line, in shell history, or in this repository. Then log
in at [http://127.0.0.1:3000](http://127.0.0.1:3000) through the SSH tunnel.

## Verification

Syntax-check the dedicated monitoring playbook:

```bash
make syntax-check-monitoring
```

Verify monitoring services through the inventory-managed SSH alias:

```bash
ssh "$MONITORING_SSH_ALIAS" 'systemctl is-active influxdb grafana-server loki loki-canary alloy tempo otelcol-contrib lv3-prometheus prometheus-alertmanager prometheus-blackbox-exporter'
```

Verify the Grafana health endpoint locally on the guest:

```bash
ssh "$MONITORING_SSH_ALIAS" 'curl -fsS http://127.0.0.1:3000/api/health'
```

## 0own Proxmox host metrics

Keep the 0own exporter bound to its Tailscale address and allow TCP 9100 only
from monitoring-lv3. Do not publish node exporter on a public or general LAN
interface. The target is declared in
`inventory/host_vars/monitoring.yml` and, when discovery is disabled, applied with the narrow playbook
`playbooks/services/prometheus-0own-node-exporter.yml`.

The 0own host exporter is published by Scanopy service discovery under the
`pve_0own_host_node_exporter_via_tailscale` job (see
`docs/runbooks/scanopy-service-discovery.md`). The general monitoring role
template now also renders the fleet scrape jobs, the public-edge probe job, and
the OpenObserve `remote_write` block from `inventory/host_vars/monitoring.yml` (empty since 2026-10-14: the push to OpenObserve was disabled; see the comment there to restore it),
so a full `grafana.yml` convergence no longer erases them. Every rendered
`prometheus.yml` is validated with `promtool` and applied with SIGHUP.

The narrow playbook `playbooks/services/prometheus-0own-node-exporter.yml`
remains for deployments that do not enable discovery
(`monitoring_scanopy_sd_enabled: false`). It validates the active
configuration, adds one managed scrape block before `remote_write`, validates
with `promtool`, sends Prometheus SIGHUP only if the file changed, and restores
its automatic backup if reload or target verification fails. While discovery is
enabled it is a no-op, because adding the static job would scrape the exporter
twice.

The 0own Proxmox host runs Debian's `prometheus-node-exporter` package. Its
systemd drop-in at
`/etc/systemd/system/prometheus-node-exporter.service.d/10-tailscale-only.conf`
binds the exporter to `100.64.0.3:9100`. The host firewall accepts
Tailscale interface traffic, and the tailnet policy restricts this metrics port
to the monitoring VM. If the host's Tailscale address changes, update both the
drop-in and the production target/grant before restarting the exporter.

Apply and verify the 0own target:

```bash
python3 scripts/ansible_scope_runner.py plan --playbook playbooks/services/prometheus-0own-node-exporter.yml --env production
python3 scripts/ansible_scope_runner.py run --playbook playbooks/services/prometheus-0own-node-exporter.yml --env production -- --limit monitoring -e '{"ansible_host":"0mcp_monitoring"}'
ssh "$MONITORING_SSH_ALIAS" 'curl -fsS --get --data-urlencode "query=up{job=\"pve_0own_host_node_exporter_via_tailscale\",monitored_host=\"proxmox-node\"}" http://127.0.0.1:9090/api/v1/query'
```

The target query should have value `1`. Useful host metrics include
`node_filesystem_avail_bytes`, `node_load1`, `node_cpu_seconds_total`, and
`node_memory_MemAvailable_bytes`. A target with value `0` indicates a scrape
or exporter availability problem; it does not by itself identify the cause.

Verify the managed overview dashboard exists and has the expected title:

```bash
ssh -t "$MONITORING_SSH_ALIAS" 'curl -fsS -u admin http://127.0.0.1:3000/api/dashboards/uid/lv3-platform-overview'
```

Verify unauthenticated public dashboard URLs do not expose dashboard content:

```bash
curl -I "${GRAFANA_URL:?Set the configured public Grafana URL}/d/<dashboard-uid>/<dashboard-slug>"
```

Expected result:

- `302 Found`
- `Location: /login...`

Verify the public edge blocks the Grafana health API and strips version headers:

```bash
curl -i "${GRAFANA_URL:?Set the configured public Grafana URL}/api/health"
curl -I "${GRAFANA_URL:?Set the configured public Grafana URL}/login"
```

Expected result:

- `/api/health` returns `404 Not Found`
- the response headers do not include `X-Grafana-Version` or `Via`

Verify the Grafana Loki datasource exists:

```bash
ssh -t "$MONITORING_SSH_ALIAS" 'curl -fsS -u admin http://127.0.0.1:3000/api/datasources/name/Loki%20Logs | jq -r '\''[.name, .type, .url] | @tsv'\'''
```

Verify the full dashboard inventory:

```bash
ssh -t "$MONITORING_SSH_ALIAS" 'curl -fsS -u admin "http://127.0.0.1:3000/api/search?query=lv3" | jq -r '\''.[] | [.uid, .title, .url] | @tsv'\'''
```

The **Build Trial Cost and CI Usage** dashboard is imported into the `LV3`
folder by the monitoring role. Open it from the Grafana dashboard list after
deployment. Its UID is deployment-prefixed; use the title rather than assuming
a fixed UID. Use cost ratios only when **Historical coverage complete** is `1`.

Verify the managed log-canary dashboard exists:

```bash
ssh -t "$MONITORING_SSH_ALIAS" 'curl -fsS -u admin http://127.0.0.1:3000/api/dashboards/uid/lv3-log-canary-overview | jq -r '\''.dashboard.title'\'''
```

Verify Loki Canary exposes metrics locally:

```bash
ssh "$MONITORING_SSH_ALIAS" 'curl -fsS http://127.0.0.1:3500/metrics | grep "^loki_canary_" | sed -n '\''1,20p'\'''
```

Verify Prometheus sees the Loki Canary target:

```bash
ssh "$MONITORING_SSH_ALIAS" 'curl -fsS --get --data-urlencode '\''query=up{job="loki-canary"}'\'' http://127.0.0.1:9090/api/v1/query | jq -c .data.result'
```

Verify Loki can still query the canary stream:

```bash
ssh "$MONITORING_SSH_ALIAS" 'start=$(date -u -d "15 minutes ago" +%s000000000); end=$(date -u +%s000000000); curl -fsSG --data-urlencode "query={name=\"loki-canary\",stream=\"stdout\"}" --data-urlencode limit=5 --data-urlencode start=$start --data-urlencode end=$end http://127.0.0.1:3100/loki/api/v1/query_range | jq -c .data.result'
```

Verify the shared-object-store cutover settings are present in Loki:

```bash
ssh "$MONITORING_SSH_ALIAS" 'sudo grep -E "object_store: s3|bucketnames: loki-chunks|delete_request_store: s3" /etc/loki/config.yml'
```

If the canary raises alerts or one of these checks fails, continue in [docs/runbooks/log-queryability-canary.md](log-queryability-canary.md).

Verify Loki currently knows about every managed host label:

```bash
ssh "$MONITORING_SSH_ALIAS" 'curl -fsS http://127.0.0.1:3100/loki/api/v1/label/host/values | jq -c .data'
```

Verify Docker container log streams are present in Loki:

```bash
ssh "$MONITORING_SSH_ALIAS" 'start=$(date -u -d "1 hour ago" +%s000000000); curl -fsSG --data-urlencode "match[]={host=\"docker-runtime\",source=\"docker\"}" --data-urlencode start=$start http://127.0.0.1:3100/loki/api/v1/series | jq -c .data'
```

Verify NGINX access logs are present in Loki:

```bash
ssh "$MONITORING_SSH_ALIAS" 'start=$(date -u -d "1 hour ago" +%s000000000); curl -fsSG --data-urlencode "match[]={host=\"nginx-edge\",service=\"nginx\",log_type=\"access\"}" --data-urlencode start=$start http://127.0.0.1:3100/loki/api/v1/series | jq -c .data'
```

If you need deterministic proof for Proxmox-host journald ingestion, emit one verification-only syslog line on the host and query it from Loki:

```bash
ssh "$PROXMOX_SSH_ALIAS" 'sudo logger -t adr0052-verification "proxmox host loki verification event"'
ssh "$MONITORING_SSH_ALIAS" 'start=$(date -u -d "10 minutes ago" +%s000000000); end=$(date -u +%s000000000); curl -fsSG --data-urlencode "query={host=\"proxmox-host\",syslog_identifier=\"adr0052-verification\"}" --data-urlencode limit=5 --data-urlencode start=$start --data-urlencode end=$end http://127.0.0.1:3100/loki/api/v1/query_range | jq -c .data.result'
```

Verify Tempo has recorded service names from traced workloads:

```bash
ssh "$MONITORING_SSH_ALIAS" 'curl -fsS http://127.0.0.1:3200/api/search/tag/service.name/values'
```

Verify Tempo service-graph metrics are present in Prometheus:

```bash
ssh "$MONITORING_SSH_ALIAS" 'curl -fsS --get --data-urlencode '\''query=traces_service_graph_request_total'\'' http://127.0.0.1:9090/api/v1/query'
```

Verify Tempo span metrics are present in Prometheus:

```bash
ssh "$MONITORING_SSH_ALIAS" 'curl -fsS --get --data-urlencode '\''query=traces_spanmetrics_calls_total'\'' http://127.0.0.1:9090/api/v1/query'
```

Verify Alertmanager is healthy:

```bash
ssh "$MONITORING_SSH_ALIAS" 'curl -fsS http://127.0.0.1:9093/-/healthy'
```

Verify the blackbox exporter is healthy:

```bash
ssh "$MONITORING_SSH_ALIAS" 'curl -fsS http://127.0.0.1:9115/-/healthy'
```

Verify nginx guest telemetry is present in InfluxDB:

```bash
ssh "$MONITORING_SSH_ALIAS" 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> filter(fn: (r) => r._measurement == "nginx" and r.host == "nginx-edge") |> limit(n: 10)'\'''
```

Verify docker build count and duration telemetry is present in InfluxDB:

```bash
ssh "$MONITORING_SSH_ALIAS" 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> filter(fn: (r) => r._measurement == "docker_builds" and r.host == "docker-build" and (r._field == "count" or r._field == "duration_ms" or r._field == "start_time_ns" or r._field == "end_time_ns")) |> limit(n: 20)'\'''
```

Verify docker runtime container telemetry is present in InfluxDB:

```bash
ssh "$MONITORING_SSH_ALIAS" 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> filter(fn: (r) => r.host == "docker-runtime" and (r._measurement == "docker_container_status" or r._measurement == "docker_container_cpu" or r._measurement == "docker_container_mem" or r._measurement == "docker_container_net" or r._measurement == "docker_container_health")) |> limit(n: 20)'\'''
```

Verify Telegraf has Docker socket access on the runtime guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'systemctl is-active telegraf && id -nG telegraf'
```

Verify local nginx `stub_status` on the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.10 'curl -fsS http://127.0.0.1:8080/basic_status'
```

Verify the Docker wrapper and Telegraf on the build guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.30 'bash -lc "command -v docker" && systemctl is-active telegraf'
```

Verify the Proxmox metric server definition on the host:

```bash
ssh "$PROXMOX_SSH_ALIAS" 'sudo pvesh get /cluster/metrics/server/influxdb-http --output-format json'
```

Verify that recent Proxmox metrics are arriving in InfluxDB:

```bash
ssh "$MONITORING_SSH_ALIAS" 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> limit(n: 5)'\'''
```

## Managed Secrets

The playbook keeps these secrets on the monitoring VM:

- `/etc/lv3/monitoring/grafana-admin-password`
- `/etc/lv3/monitoring/influxdb-admin-password`
- `/etc/lv3/monitoring/influxdb-operator.token`
- `/etc/lv3/monitoring/influxdb-proxmox-writer.token`
- `/etc/lv3/monitoring/influxdb-guest-writer.token`
- `/etc/lv3/monitoring/grafana-reader.token`

Deployments whose config prefix is not a valid POSIX prefix may have older
copies under `/etc/<config-prefix>/monitoring`. The role checks that legacy
directory before reading, generating, or reconciling credentials and copies
existing values into the canonical unix-prefix directory without rotating
Grafana or InfluxDB authority. Keep the legacy copies until the canonical
converge and all monitoring probes have passed.

For an initialized InfluxDB runtime, the role also proves that the managed
operator-token file can enumerate the organization catalog. If that file is
stale, `/root/.influxdbv2/configs` is considered only as a recovery candidate;
its active default token must pass the same live API check before the managed
file is replaced. If neither token authenticates, stop and perform supported
offline InfluxDB recovery rather than deleting authorization records.

If the accepted token exposes only a historical organization name, set
`monitoring_influxdb_legacy_org_name` in the deployment-local identity overlay
after verifying the catalog. The role renames that exact organization only when
the desired organization is absent, preserving its ID, buckets, and token
authorizations. It then aligns the root CLI default and binds all bucket and
authorization reconciliation to the preserved organization ID. An absent or
ambiguous match stops convergence.

When a deployment retains a Prometheus unit from an earlier config-prefix,
declare only that verified unit in `monitoring_prometheus_legacy_service_names`
inside the deployment-local identity overlay. The monitoring role stops and
disables it before starting the canonical unit, and Alertmanager always restarts
the canonical service-name variable rather than a hard-coded unit.

The control machine keeps one mirrored token outside git for host-side Proxmox configuration:

- `.local/monitoring/proxmox-writer.token`
- `.local/monitoring/guest-writer.token`
- `.local/monitoring/loki-minio-secret-key.txt`

The shared trace ingress for instrumented private services is:

- OTLP gRPC: inventory-resolved monitoring address on port `4317`
- OTLP HTTP: inventory-resolved monitoring address on port `4318`, path `/v1/traces`

If the mirrored local token is missing, rerun `make converge-monitoring` from the control machine.

## Recovery Note

During the live rollout on 2026-03-22, VMs `110`, `120`, `130`, and `140` again had stale netplan MAC metadata and the Proxmox host returned `Destination Host Unreachable` for the private guest IPs.

The repair used the existing guest-agent flow from the netplan drift runbook before rerunning the monitoring playbook:

```bash
ssh "$PROXMOX_SSH_ALIAS" 'sudo qm config 110 | grep ^net0 && sudo qm config 120 | grep ^net0 && sudo qm config 130 | grep ^net0 && sudo qm config 140 | grep ^net0'
ssh "$PROXMOX_SSH_ALIAS" "sudo qm guest exec 110 -- bash -lc 'sed -i \"s/bc:24:11:94:37:83/bc:24:11:0d:03:bb/\" /etc/netplan/50-cloud-init.yaml && netplan apply'"
ssh "$PROXMOX_SSH_ALIAS" "sudo qm guest exec 120 -- bash -lc 'sed -i \"s/bc:24:11:b0:d4:d1/bc:24:11:aa:99:7c/\" /etc/netplan/50-cloud-init.yaml && netplan apply'"
ssh "$PROXMOX_SSH_ALIAS" "sudo qm guest exec 130 -- bash -lc 'sed -i \"s/bc:24:11:7c:4e:5b/bc:24:11:0f:8a:f2/\" /etc/netplan/50-cloud-init.yaml && netplan apply'"
ssh "$PROXMOX_SSH_ALIAS" "sudo qm guest exec 140 -- bash -lc 'sed -i \"s/bc:24:11:82:c6:38/bc:24:11:b1:76:a0/\" /etc/netplan/50-cloud-init.yaml && netplan apply'"
```
