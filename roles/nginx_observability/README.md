# nginx_observability

Adds guest-local NGINX service telemetry through `stub_status` and Telegraf.

Inputs: stub-status paths and URL, Telegraf config path, observability directories, and guest writer token paths.
Outputs: loopback-only `stub_status`, Telegraf on the guest, and nginx metrics in InfluxDB.
