# ADR 0401: Remove Netdata from the Platform

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.92
- Implemented In Platform Version: not yet applied
- Implemented On: 2026-04-10
- Date: 2026-04-10
- Concern: Service Lifecycle, Observability Consolidation
- Depends on: ADR 0196 (Netdata Realtime Streaming Metrics), ADR 0389 (Service Decommissioning Procedure), ADR 0396 (Deterministic Service Decommissioning)
- Tags: lifecycle, decommissioning, netdata, realtime, monitoring, removal

---

## Context

Netdata was introduced in ADR 0196 as a real-time per-host metrics collection
and streaming system. The architecture used a parent agent on `monitoring`
(port 19999) with child agents installed on every guest VM and the Proxmox host,
streaming metrics to the parent over an authenticated connection. Prometheus
scraped the parent via `/api/v1/allmetrics?format=prometheus_all_hosts`.

### Gap analysis: Netdata vs Prometheus + Grafana

| Capability | Netdata | Prometheus + Grafana |
|---|---|---|
| Per-process CPU/memory breakdown | Yes (real-time) | node_exporter: process-level via process-exporter add-on |
| Host-level CPU, memory, disk, net | Yes | node_exporter: full coverage |
| Disk I/O per-device metrics | Yes | node_exporter: full coverage |
| Network interface metrics | Yes | node_exporter: full coverage |
| Systemd unit state | Yes | node_exporter: full coverage |
| Container metrics (Docker) | Yes | cAdvisor already deployed |
| Real-time browser dashboard | Yes | Grafana: dashboard 1860 (Node Exporter Full) |
| Custom alert rules | Yes (Netdata health) | Prometheus alertmanager (already used for all SLOs) |
| Metric retention (long-term) | 1 day ephemeral | Prometheus: 15d (configurable) |
| SLO integration | No | Prometheus recording + alerting rules (full platform SLOs) |
| Cross-host aggregation | Parent/child | Prometheus federation (already in use) |
| Grafana integration | Plugin required | Native data source (Prometheus) |

### Why remove Netdata

1. **Coverage overlap**: Every metric Netdata collected is also collected by
   `node_exporter` (installed on all guests) and forwarded to Prometheus on
   `monitoring`. The Grafana dashboard `1860 - Node Exporter Full` provides
   equivalent browser-based real-time visibility.

2. **Complexity without benefit**: Netdata's parent-child streaming added an
   additional authentication surface (`netdata-stream-api-key`), a custom
   Prometheus scrape job, and Netdata child agents on every host. This doubled
   the observability agent footprint.

3. **Architectural alignment**: The platform observability stack is
   Prometheus-native. Netdata is an independent system that required special
   casing in catalogs, playbooks, and the nginx edge (realtime.example.com).

4. **Active browser dashboards**: The real-time browser dashboard at
   `realtime.example.com` was the most-cited reason to keep Netdata. Grafana's
   Node Exporter Full dashboard (UID `1860`) provides equivalent capability
   with the same data freshness (15s scrape interval).

### Removal scope

| Category | Files | Key items |
|---|---|---|
| Ansible roles | 1 | `netdata_runtime` (fully deleted) |
| Playbooks | 3 | `realtime.yml` (collection + services/), deleted |
| Observability groups | 3 | `observability.yml`, `monitoring-stack.yml` |
| Inventory/config | 4 | `proxmox-host.yml`, `platform.yml`, port assignments |
| Config catalogs | 15 | Full CATALOG_REGISTRY sweep via ADR 0396 decommission script |
| Tests | 4 | netdata role test, realtime playbook test, nginx edge test |
| Scripts | 3 | `recover_local_secrets.sh`, `generate_platform_vars.py`, `ops_portal/app.py` |
| ADR | 1 | ADR 0196 → Deprecated |

---

## Decision

Remove Netdata (`realtime` service) from the platform following ADR 0389's
decommissioning procedure, using the ADR 0396 `decommission_service.py` script
for catalog cleanup.

### Phase 1: Production Teardown

Run on `monitoring` and all guest VMs:

```bash
sudo systemctl stop netdata netdata-parent || true
sudo apt-get remove --purge netdata netdata-agent netdata-core -y || true
sudo rm -rf /etc/netdata /var/lib/netdata /var/cache/netdata
```

On the Proxmox host:

```bash
apt-get remove --purge netdata -y || true
```

### Phase 2: Code Purge

Executed via `decommission_service.py`:

```bash
python3 scripts/decommission_service.py --service realtime --purge-code --confirm realtime
```

Additional manual cleanup:
- `collections/ansible_collections/lv3/platform/roles/netdata_runtime/` — deleted
- `playbooks/services/realtime.yml` — deleted
- `playbooks/groups/observability.yml` — removed realtime import
- `playbooks/monitoring-stack.yml` — removed realtime import
- `collections/.../playbooks/groups/observability.yml` — removed realtime import
- `collections/.../roles/monitoring_vm/templates/prometheus.yml.j2` — removed netdata scrape job
- `collections/.../roles/monitoring_vm/defaults/main.yml` — removed `monitoring_netdata_parent_port` and `monitoring_netdata_parent_metrics_url`
- `collections/.../roles/nginx_edge_publication/defaults/main.yml` — removed realtime CSP and auth entries
- `inventory/host_vars/proxmox-host.yml` — removed `netdata_port` from port assignments, removed `lv3_service_topology.realtime` block
- `inventory/group_vars/platform.yml` — removed all `netdata_port: 19999` entries

### Phase 3: Live Teardown Verification

After next full platform converge, verify:

```bash
# Confirm no netdata process running on monitoring
ssh monitoring "pgrep netdata || echo 'Netdata not running (expected)'"

# Confirm Prometheus no longer has netdata scrape targets
curl -s http://monitoring:9090/api/v1/targets | python3 -m json.tool | grep -c netdata || echo '0 (expected)'

# Confirm realtime.example.com returns 404 or is deprovisioned
curl -o /dev/null -s -w "%{http_code}" https://realtime.example.com
```

---

## Consequences

**Positive:**
- Eliminates one independent observability agent from every host (~10 hosts)
- Removes `netdata-stream-api-key` secret management surface
- Removes `realtime.example.com` nginx edge publication
- Full host metrics coverage maintained via `node_exporter` (already deployed)
- Alerting coverage maintained via Prometheus alertmanager (already used)
- Browser dashboards maintained via Grafana Node Exporter Full (dashboard 1860)

**Negative:**
- Per-process CPU breakdown requires `process-exporter` if needed in future
- Real-time per-second metrics resolution: Prometheus default is 15s scrape;
  Netdata offered 1s resolution. For platform operational use, 15s is sufficient.

**Mitigations:**
- Install Grafana dashboard 1860 (Node Exporter Full) for equivalent real-time
  host metrics visualization
- If per-process breakdown is needed, add `prometheus-process-exporter` package
  to `monitoring_stack_packages` (tracked as future enhancement, not blocking)
