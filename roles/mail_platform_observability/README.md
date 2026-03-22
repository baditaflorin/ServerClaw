# mail_platform_observability

Ships mail-platform telemetry from the Docker runtime VM into the shared InfluxDB and Grafana path.

Inputs: mail platform local state paths, Stalwart admin credentials, mailbox credentials, and monitoring token paths.
Outputs: Telegraf-based mail telemetry covering queue depth, mailbox count, send counters, fallback usage, and selected Stalwart server counters.
