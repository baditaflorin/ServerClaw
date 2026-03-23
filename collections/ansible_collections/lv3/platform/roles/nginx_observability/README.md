# nginx_observability

Adds guest-local NGINX service telemetry through `stub_status` and Telegraf.

Inputs: stub-status paths and URL, Telegraf config path, service identity, and the shared `guest_observability` framework inputs.
Outputs: loopback-only `stub_status`, a framework-managed Telegraf path on the guest, and nginx metrics in InfluxDB.
