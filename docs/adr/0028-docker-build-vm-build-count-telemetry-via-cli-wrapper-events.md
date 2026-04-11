# ADR 0028: Docker Build VM Build Count And Duration Telemetry Via CLI Wrapper Events

- Status: Accepted
- Implementation Status: Implemented on workstream branch
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

ADR 0011 established the monitoring VM, InfluxDB bucket, and managed Grafana dashboards, but the Docker build guest is still only visible at the VM resource level.

That is not enough for build operations. For `docker-build`, we also need direct answers to basic operator questions:

- how many Docker builds were actually started on the build VM
- how long those builds took

This count should be gathered without inventing a parallel monitoring stack, without exposing new public endpoints, and without depending on manual Grafana clicks.

## Decision

We will count Docker builds on `docker-build` by using a repo-managed Docker CLI wrapper and the existing guest-to-monitoring telemetry path.

The implementation is:

1. Install a repo-managed `docker` wrapper on `docker-build`.
   - place the wrapper at `/usr/local/bin/docker`
   - delegate real CLI execution to `/usr/bin/docker`
   - record build start time, end time, exit code, and duration
   - emit a single local telemetry event after every `docker build`, `docker buildx build`, `docker buildx bake`, or `docker compose build`
2. Install Telegraf on `docker-build`.
   - listen for local UDP line protocol events on loopback
   - write the resulting `docker_builds` measurement into the existing InfluxDB bucket on `monitoring`
3. Reuse the existing guest-writer token lifecycle from the monitoring stack.
   - the token is still created on the monitoring VM
   - the token is mirrored locally on the control machine and copied to the build VM during convergence
4. Extend the managed Grafana dashboards.
   - add build-count panels to the platform overview
   - add build-duration panels to the platform overview and the `LV3 docker-build Detail` dashboard

The first tracked event schema is:

- measurement: `docker_builds`
- field: `count=1`
- tags: `host`, `command`, `status`
- fields: `exit_code`, `start_time_ns`, `end_time_ns`, `duration_ms`

## Security posture

- build telemetry is generated only on the private build guest
- the local event listener is loopback-only on the build guest
- guest telemetry continues to use the private path to `10.10.10.40`
- no InfluxDB token is committed to git
- Grafana remains the only published presentation layer

## Consequences

- build activity becomes visible separately from CPU or disk pressure
- Grafana can answer both "how many builds did we run" and "how long did they take" directly from managed dashboards
- the implementation stays inside the current InfluxDB plus Grafana architecture
- the build guest now has a small but explicit wrapper surface that later build-host baseline work must preserve

## Follow-up requirements

- if operators later need per-user, per-project, or richer per-build metadata, define that as a separate change instead of overloading the wrapper event stream
- if build activity later needs to include non-CLI paths such as direct daemon or API-driven builds, define that explicitly as a follow-up instead of assuming the wrapper covers them

## Sources

- <https://docs.influxdata.com/telegraf/v1/input-plugins/>
