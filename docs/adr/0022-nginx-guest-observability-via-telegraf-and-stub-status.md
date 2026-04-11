# ADR 0022: NGINX Guest Observability Via Telegraf And Stub Status

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.25.0
- Implemented In Platform Version: 0.16.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

ADR 0011 established that the platform should monitor both the Proxmox control plane and guest internals in a predictable way.

The first implemented dashboard covered VM-level metrics for `nginx-edge`, but that is not enough to understand the public edge service itself. We also need service-level visibility for the NGINX process:

- active connections
- requests over time
- accepts and handled rates
- reading, writing, and waiting connection states

This telemetry must remain infrastructure-as-code, must reuse the existing InfluxDB plus Grafana stack on `10.10.10.40`, and must not expose operational endpoints publicly.

## Decision

We will monitor the NGINX guest with a guest-local telemetry path built from:

1. NGINX `stub_status`
   - enabled only on loopback
   - exposed on `127.0.0.1:8080/basic_status`
   - not published through the public edge
2. Telegraf on `nginx-edge`
   - scrapes the local `stub_status` endpoint
   - also captures guest system metrics such as CPU, memory, disk, network, and processes
   - writes to the existing InfluxDB bucket on the monitoring VM
3. Grafana dashboard extensions
   - the managed `LV3 Platform Overview` dashboard must include NGINX service panels in addition to VM-level panels

Token handling:

- guest-side telemetry uses a dedicated InfluxDB guest-writer token
- the token is generated and mirrored by the monitoring role
- the token is stored locally on the guest outside git

## Security posture

- `stub_status` is loopback-only and denied to non-local access
- the public NGINX edge does not publish the observability endpoint
- telemetry reuses the private network path to the monitoring VM
- no guest telemetry secret is committed to git

## Consequences

- the NGINX VM becomes observable at both VM and service level
- Grafana can distinguish VM pressure from NGINX request-path pressure
- the guest-observability path becomes reusable for future service-level telemetry on other guests
- the monitoring stack now has an explicit guest-writer token lifecycle to manage

## Follow-up requirements

- if richer NGINX metrics are needed later, decide whether to stay on `stub_status` or introduce a dedicated exporter with a new ADR update
- if logs should be centralized, define the log shipping and retention path explicitly instead of mixing it into this ADR implicitly

## Sources

- <https://nginx.org/en/docs/http/ngx_http_stub_status_module.html>
- <https://docs.influxdata.com/telegraf/v1/input-plugins/nginx/>
