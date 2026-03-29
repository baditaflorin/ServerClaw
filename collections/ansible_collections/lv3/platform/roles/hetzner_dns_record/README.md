# hetzner_dns_record

Converges a single Hetzner DNS record through the API.
Raw Hetzner payloads are translated into canonical DNS facts before matching or drift logic runs.

Inputs: zone name, record name, type, value, TTL, and the API token environment variable.
Outputs: one idempotently managed DNS record in the target Hetzner zone.
