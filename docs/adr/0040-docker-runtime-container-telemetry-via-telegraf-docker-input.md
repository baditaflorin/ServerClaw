# ADR 0040: Docker Runtime Container Telemetry Via Telegraf Docker Input

- Status: Accepted
- Implementation Status: Implemented on workstream branch
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

ADR 0011 established VM-level dashboards and guest-local service telemetry patterns, but `docker-runtime-lv3` is still mostly opaque once containers are running.

Today the managed dashboard for `docker-runtime-lv3` answers only VM questions such as:

- how busy the VM CPU is
- how full VM memory and disk are
- whether the VM itself is up

That is not enough for runtime operations. For the Docker runtime VM we also need repo-managed answers to basic container questions:

- how many containers are currently running
- which containers are consuming CPU or memory
- whether container health checks are failing
- what the current container snapshot looks like without clicking through ad hoc host commands

We want that detail without introducing a second monitoring stack, without exposing a new public endpoint, and without relying on hand-edited Grafana dashboards.

## Decision

We will collect container runtime telemetry on `docker-runtime-lv3` by reusing the shared guest observability framework and Telegraf's Docker input plugin.

The implementation is:

1. Add a dedicated `docker_runtime_observability` role.
   - reuse `roles/guest_observability` for Telegraf installation, token handling, and service verification
   - render a service-specific Telegraf fragment for Docker container telemetry
2. Collect metrics directly from the local Docker Engine API.
   - use the local Unix socket at `/var/run/docker.sock`
   - add `telegraf` to the local `docker` group so the plugin can read container state
   - collect the standard `docker_container_cpu`, `docker_container_mem`, `docker_container_net`, `docker_container_status`, and `docker_container_health` measurements
3. Keep the telemetry inside the existing private monitoring path.
   - continue writing into the existing InfluxDB bucket on `monitoring-lv3`
   - continue provisioning Grafana dashboards from repo-managed JSON templates
4. Extend the managed `LV3 docker-runtime-lv3 Detail` dashboard.
   - add container-count, aggregate CPU, aggregate memory, and unhealthy-container stats
   - add per-container CPU, memory, and network panels
   - add a table snapshot for container image, status, health, PID, exit code, and uptime

## Security posture

- telemetry is collected only from the private runtime VM
- no new public listener is exposed for runtime telemetry
- the Docker socket remains local-only, but giving `telegraf` access to it expands host attack surface and must remain under repo-managed, root-owned configuration
- guest-to-monitoring writes still use the existing guest writer token and private address path

## Consequences

- runtime operators can distinguish VM pressure from per-container behavior directly in Grafana
- container health failures become visible without interactive Docker inspection
- the monitoring stack gains another thin service-specific observability role instead of duplicating Telegraf plumbing
- changes that harden Docker socket access later must preserve the telemetry contract explicitly

## Follow-up requirements

- if operators later need per-compose-project rollups or non-running container history, define that as a separate change instead of overloading the first dashboard slice
- if long-term retention or alerting should use container health state, define alert rules separately instead of assuming the dashboard alone is sufficient

## Sources

- <https://docs.docker.com/engine/security/#docker-daemon-attack-surface>
- <https://docs.influxdata.com/telegraf/v1/input-plugins/>
- <https://github.com/influxdata/telegraf/tree/master/plugins/inputs/docker>
