# Monitoring Stack Runbook

## Purpose

This runbook converges the dedicated monitoring VM `140` at `10.10.10.40` with:

- Grafana on port `3000`
- InfluxDB 2 on port `8086`
- a provisioned Grafana data source for the Proxmox metrics bucket
- a provisioned Grafana folder, `LV3`
- a provisioned overview dashboard, `LV3 Platform Overview`
- a provisioned detail dashboard for each managed VM
- guest-side NGINX telemetry from `nginx-lv3`
- a Proxmox external metric server that writes into InfluxDB over the private network

Grafana is available both on the private VM and at [https://grafana.lv3.org](https://grafana.lv3.org).

## Command

```bash
make converge-monitoring
```

## What the playbook does

1. Adds the Grafana and InfluxData APT repositories on `monitoring-lv3`.
2. Installs and starts `grafana`, `influxdb2`, and `influxdb2-cli`.
3. Initializes InfluxDB with the `lv3` organization and the `proxmox` bucket.
4. Creates separate InfluxDB tokens for Proxmox metric writes and Grafana bucket reads.
5. Provisions the Grafana InfluxDB data source automatically.
6. Creates a dedicated guest-writer token for guest-side telemetry and mirrors it to `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/monitoring/guest-writer.token`.
7. Renders the managed dashboard JSON from repo and imports the overview plus VM detail dashboards into Grafana over the local Grafana API.
8. Creates or updates the Proxmox metric server `influxdb-http` to send metrics to `10.10.10.40:8086`.
9. Converges `nginx-lv3` with loopback-only `stub_status` and Telegraf shipping guest and nginx service telemetry into InfluxDB.

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
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'systemctl is-active influxdb grafana-server'
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

Verify nginx guest telemetry is present in InfluxDB:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'sudo influx query --host http://127.0.0.1:8086 --org lv3 --token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '\''from(bucket: "proxmox") |> range(start: -15m) |> filter(fn: (r) => r._measurement == "nginx" and r.host == "nginx-lv3") |> limit(n: 10)'\'''
```

Verify local nginx `stub_status` on the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.10 'curl -fsS http://127.0.0.1:8080/basic_status'
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

If the mirrored local token is missing, rerun `make converge-monitoring` from the control machine.
