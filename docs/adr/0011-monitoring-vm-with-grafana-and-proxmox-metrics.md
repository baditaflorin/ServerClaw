# ADR 0011: Monitoring VM With Grafana And Proxmox Metrics

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.23.0
- Implemented In Platform Version: 0.15.0
- Implemented On: 2026-03-22
- Date: 2026-03-21

## Context

The platform needs predictable monitoring for:

- the Proxmox host itself
- Proxmox-managed guests
- the Docker runtime VM
- the Docker build VM
- ingress and service health over time

Monitoring must not be an afterthought embedded into unrelated guests. It needs a clear home, stable data flow, and a simple enough design that both humans and agents can understand and operate it.

Proxmox VE natively supports external metric servers and can send host, guest, and storage metrics to InfluxDB. Grafana is the intended visualization layer.

## Decision

We will create a dedicated monitoring VM on the internal Proxmox network.

Initial role and address:

- `10.10.10.40`
- purpose: centralized monitoring and dashboards

Initial software responsibilities:

1. Grafana
   - dashboards
   - alert views
   - operational visualization
2. InfluxDB
   - receive native Proxmox metrics from the Proxmox external metric server feature
3. Grafana Alloy
   - collect Prometheus-style metrics and logs from monitored Linux guests where needed
   - forward or expose telemetry for Grafana consumption

## Monitoring model

We will use two telemetry paths on purpose:

1. Proxmox-native path
   - Proxmox host sends platform metrics to InfluxDB
   - use this for node, VM, CT, and storage visibility from the Proxmox control plane
2. Guest-level path
   - monitored VMs expose system and service metrics
   - use Grafana Alloy and exporters for guest internals, Docker/container visibility, and service-level telemetry

This split is deliberate:

- Proxmox is the source of truth for virtualization/platform metrics
- guest collectors are the source of truth for in-guest process, container, and OS metrics

## Phase-one implementation decisions

The first converged implementation keeps the monitoring stack on the dedicated monitoring VM and manages it from code.

- Grafana runs on VM `140`.
- InfluxDB 2 receives Proxmox metrics through the native Proxmox external metric server integration over HTTP on the private network.
- Grafana is provisioned with an InfluxDB data source automatically from locally generated secrets on the monitoring VM.
- Grafana contains a managed high-level dashboard, `LV3 Platform Overview`, plus one managed detail dashboard per VM.
- Grafana is published at `https://grafana.lv3.org` through the NGINX edge.

## Scope of the first monitoring rollout

Phase one should cover at least:

1. Proxmox host health
   - CPU
   - RAM
   - load
   - disk usage
   - storage health
   - VM resource pressure
2. NGINX VM
   - VM uptime
   - system resources
   - ingress/service reachability
3. Docker runtime VM
   - VM resources
   - Docker/container metrics
   - container restarts and failures
4. Docker build VM
   - VM resources
   - build throughput pressure
   - disk pressure
   - high CPU and memory alerts

## Consequences

- Monitoring gets its own isolated lifecycle and does not compete conceptually with ingress or runtime workloads.
- Proxmox metrics remain available even if guest-level collectors are incomplete.
- Guest-level observability can evolve per role without redesigning the platform telemetry path.
- The monitoring VM becomes critical infrastructure and must be backed up accordingly.

## Follow-up requirements

This ADR defines the topology and data-flow direction. Follow-up automation should still define:

- VM sizing for the monitoring node
- retention policy for metrics and logs
- alert destinations
- exact Alloy/exporter deployment strategy on each monitored guest

## Implemented state

The implemented dashboard set currently covers:

- Proxmox host load, CPU, memory, and disk usage
- `nginx-lv3` CPU, memory, disk, and network throughput
- `nginx-lv3` NGINX service telemetry from loopback-only `stub_status`
- `docker-runtime-lv3` CPU, memory, disk, and network throughput
- `docker-build-lv3` CPU, memory, disk, and network throughput
- `monitoring-lv3` CPU, memory, disk, and network throughput

The implemented Grafana structure currently includes:

- folder `LV3`
- overview dashboard `LV3 Platform Overview`
- detail dashboard `LV3 nginx-lv3 Detail`
- detail dashboard `LV3 docker-runtime-lv3 Detail`
- detail dashboard `LV3 docker-build-lv3 Detail`
- detail dashboard `LV3 monitoring-lv3 Detail`

The implemented guest-level telemetry currently includes:

- `nginx-lv3` Telegraf shipping guest metrics into InfluxDB
- `nginx-lv3` NGINX active connections, accepts, handled, requests, and connection-state visibility in Grafana

## Sources

- <https://pve.proxmox.com/wiki/External_metric_server>
- <https://pve.proxmox.com/pve-docs/index.html>
- <https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.exporter.cadvisor/>
