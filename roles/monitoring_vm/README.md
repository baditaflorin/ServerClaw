# monitoring_vm

Builds the monitoring VM stack with InfluxDB, Grafana, tokens, and managed dashboards.

Inputs: monitoring paths, Grafana and InfluxDB settings, local artifact paths, and a `proxmox_hosts` inventory group.
Outputs: a running monitoring stack plus mirrored writer tokens and provisioned dashboard JSON.
