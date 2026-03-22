# Workstream ADR 0053: OpenTelemetry Traces And Service Maps With Grafana Tempo

- ADR: [ADR 0053](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0053-opentelemetry-traces-and-service-maps-with-grafana-tempo.md)
- Title: Distributed tracing and service maps for internal apps and workflows
- Status: merged
- Branch: `codex/adr-0053-tempo-traces`
- Worktree: `../proxmox_florin_server-tempo-traces`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0052-loki-logs`
- Conflicts With: none
- Shared Surfaces: `monitoring-lv3`, Grafana, internal APIs, workflow execution

## Scope

- choose Tempo and OpenTelemetry for trace collection
- define naming, collector, and first-instrumentation boundaries
- align traces with the existing Grafana monitoring model

## Non-Goals

- tracing every service before the first implementation
- public publication of internal tracing endpoints

## Expected Repo Surfaces

- `docs/adr/0053-opentelemetry-traces-and-service-maps-with-grafana-tempo.md`
- `docs/workstreams/adr-0053-tempo-traces.md`
- `docs/runbooks/monitoring-stack.md`
- `docs/runbooks/configure-mail-platform.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `roles/monitoring_vm/`
- `roles/mail_platform_runtime/`
- `workstreams.yaml`

## Expected Live Surfaces

- Tempo, Prometheus, and a shared OTLP collector integrated into `monitoring-lv3`
- Grafana Tempo and Prometheus datasources provisioned on the monitoring plane
- mail gateway traces flowing from `docker-runtime-lv3` into Tempo with service-graph edges for Stalwart and Brevo calls

## Verification

- `make syntax-check-monitoring`
- `make syntax-check-mail-platform`
- `make converge-monitoring`
- `HETZNER_DNS_API_TOKEN=... make converge-mail-platform`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'systemctl is-active grafana-server influxdb tempo otelcol-contrib lv3-prometheus'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'curl -fsS http://127.0.0.1:3200/api/search/tag/service.name/values'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'curl -fsS --get --data-urlencode '\''query=traces_service_graph_request_total'\'' http://127.0.0.1:9090/api/v1/query'`

## Merge Criteria

- Tempo, Prometheus, and the OTLP collector converge cleanly from `main`
- at least one repo-managed internal service emits traces and produces service-graph metrics in Grafana

## Notes For The Next Assistant

- add more instrumented internal paths by pointing them at the shared OTLP endpoint on `monitoring-lv3`
