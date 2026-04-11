# docker_runtime_observability

Collects Docker container runtime telemetry from `docker-runtime` through Telegraf's Docker input plugin.

Inputs: Telegraf config path, Docker socket endpoint, service identity, optional label filters, and the shared `guest_observability` framework inputs.
Outputs: a framework-managed Telegraf configuration, `telegraf` access to the local Docker socket, and `docker_container_*` measurements in InfluxDB.
