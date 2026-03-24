# ADR 0150: Dozzle for Real-Time Container Log Access

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform has Loki (ADR 0052) for centralised log aggregation and Grafana for log querying. Loki is the right tool for log retention, search across time windows, and correlation with metrics. However, it has a significant gap for one specific use case: **real-time container log tailing during deployment, debugging, or incident response**.

The Loki ingestion pipeline (Promtail → Loki → Grafana) introduces latency: logs typically appear in Grafana 15–60 seconds after being written. For a deployment that is actively running, an operator watching for errors needs to see log lines in under 1 second.

The current approaches for real-time logs are:
- SSH to `docker-runtime-lv3` and run `docker logs -f <container>`. This works but requires SSH access, knowledge of the container name, and produces raw log output without syntax highlighting or multi-container aggregation.
- Portainer (ADR 0055) provides a container log view in its UI but is designed for read-mostly Docker runtime operations and its log view does not support multi-container tailing or advanced filtering.
- Windmill's job log stream is available during execution but does not show the underlying container logs if the Windmill job is running Ansible or Docker Compose operations.

**Dozzle** is a lightweight, read-only container log viewer with:
- A browser UI that streams Docker container logs in real time via Server-Sent Events (SSE).
- Multi-container log aggregation (tail multiple containers simultaneously in a split view).
- Regex filtering and syntax highlighting.
- A REST API (`/api/logs/stream/<container>`) for programmatic log streaming.
- Agent mode that aggregates logs from multiple Docker hosts into one view.
- Read-only access: Dozzle cannot start, stop, or modify containers.

Dozzle fills the gap between Portainer (management UI) and Loki (historical analysis) for the real-time debugging use case.

## Decision

We will deploy **Dozzle** on each Docker VM (`docker-runtime-lv3`, `docker-build-lv3`, `monitoring-lv3`) in agent mode, with a single hub instance on `docker-runtime-lv3` that aggregates logs from all agents.

### Deployment

```yaml
# Hub instance on docker-runtime-lv3
- service: dozzle-hub
  vm: docker-runtime-lv3
  image: amir20/dozzle:latest
  port: 8882
  access: tailscale_only
  subdomain: logs.lv3.org   # Tailscale-only
  mode: hub
  agents:
    - docker-runtime-lv3:7007
    - docker-build-lv3:7007
    - monitoring-lv3:7007

# Agent instance on each Docker VM (runs alongside each VM's containers)
- service: dozzle-agent
  image: amir20/dozzle:latest
  port: 7007
  access: internal_only
  mode: agent
```

### Authentication

Dozzle's native auth is simple HTTP basic auth or no auth. For the platform, authentication is enforced at the nginx level via the OAuth2-proxy pattern (ADR 0133):

```nginx
# logs.lv3.org vhost
location / {
    auth_request /oauth2/auth;
    error_page 401 = /oauth2/sign_in;
    proxy_pass http://dozzle-hub:8882;
    # SSE support
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600;
}
```

### API integration for agents

The Dozzle REST API enables agents to stream or retrieve recent logs during diagnostics:

```python
# platform/diagnostics/containers.py

class ContainerLogClient:
    def stream(self, container: str, lines: int = 100) -> Iterator[str]:
        """Stream the last N lines plus new lines as they arrive (SSE)."""
        response = requests.get(
            f"http://dozzle-hub:8882/api/logs/stream/{container}",
            stream=True,
            headers={"Accept": "text/event-stream"},
        )
        for line in response.iter_lines():
            if line.startswith(b"data:"):
                yield line[5:].decode("utf-8")

    def tail(self, container: str, lines: int = 50) -> list[str]:
        """Return the last N log lines (non-streaming)."""
        response = requests.get(
            f"http://dozzle-hub:8882/api/logs/{container}?n={lines}",
        )
        return response.json()["logs"]
```

The triage engine (ADR 0114) uses the Dozzle API as an alternative to Loki for signal extraction when real-time accuracy is more important than historical depth:

```python
# In triage engine signal extraction
if self.signal_requires_realtime(signal_name):
    # Use Dozzle for last 50 lines (sub-second freshness)
    recent_logs = container_logs.tail(service_to_container(service), lines=50)
else:
    # Use Loki for historical queries (15-second latency acceptable)
    recent_logs = loki.query(...)
```

### Runbook executor integration

The runbook executor (ADR 0129) uses Dozzle to verify that a restarted container is producing healthy log output after a restart step:

```yaml
# In a runbook step that restarts a service
- id: restart-service
  type: mutation
  workflow_id: restart-container
  params:
    container: "{{ container_name }}"
  success_condition: "result.exit_code == 0"

- id: verify-log-output
  type: diagnostic
  description: Confirm container is producing expected startup log lines
  workflow_id: check-container-logs
  params:
    container: "{{ container_name }}"
    expected_pattern: "{{ service_ready_log_pattern }}"
    timeout_seconds: 30
  success_condition: "result.pattern_found == true"
```

## Consequences

**Positive**

- Real-time log tailing is available to operators via a browser without SSH access to the Docker VM. This is especially useful during deployments where the operator is watching for startup errors.
- The multi-container aggregate view (all containers on all Docker VMs in one browser tab) reduces context switching during incident response.
- The Dozzle API gives the triage engine real-time log access that is fresher than Loki's 15-60 second ingestion latency.

**Negative / Trade-offs**

- Dozzle is read-only and has no persistent log storage. It is a real-time view only; logs older than the Docker container's stdout buffer are not accessible via Dozzle. Historical analysis requires Loki.
- The SSE streaming connection to `logs.lv3.org` keeps a long-lived HTTP connection open from the operator's browser. If many operators are tailing logs simultaneously, this multiplies the load on the nginx proxy.
- Dozzle exposes container names and log content to any authenticated operator. Containers that log sensitive data (e.g., OpenBao audit logs, Keycloak session logs) should have log scrubbing configured at the container level before Dozzle is deployed.

## Boundaries

- Dozzle is for real-time log viewing. Retention, search, and alerting on log content are handled by Loki (ADR 0052).
- Dozzle is read-only. Container management (start, stop, restart) continues through the platform CLI, Portainer, or Windmill.

## Related ADRs

- ADR 0052: Grafana Loki (log retention and historical search; complementary to Dozzle)
- ADR 0055: Portainer (container management; different use case from Dozzle)
- ADR 0114: Rule-based incident triage engine (uses Dozzle API for real-time signals)
- ADR 0129: Runbook automation executor (log verification step)
- ADR 0133: Portal authentication by default (OAuth2-proxy gate on logs.lv3.org)
