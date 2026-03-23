# monitoring_vm

Builds the monitoring VM stack with InfluxDB, Grafana, Prometheus, Tempo, a shared OTLP collector, tokens, and managed dashboards.

Inputs: monitoring paths, Grafana and InfluxDB settings, Tempo and collector package pins, local artifact paths, and a `proxmox_hosts` inventory group.
Outputs: a running monitoring stack plus mirrored writer tokens, provisioned dashboards, Prometheus service-graph metrics, and Tempo-backed trace storage.
