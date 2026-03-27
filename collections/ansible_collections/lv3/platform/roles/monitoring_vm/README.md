# monitoring_vm

Builds the monitoring VM stack with InfluxDB, Grafana, Prometheus, blackbox exporter, Tempo, a shared OTLP collector, tokens, and managed dashboards.

Inputs: monitoring paths, Grafana and InfluxDB settings, SLO source artifacts, Tempo and collector package pins, local artifact paths, and a `proxmox_hosts` inventory group.
Outputs: a running monitoring stack plus mirrored writer tokens, provisioned dashboards, Prometheus service-graph metrics, blackbox-driven SLO rules and alerts, and Tempo-backed trace storage.
