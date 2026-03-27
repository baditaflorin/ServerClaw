# hetzner_dns_record

Converges a single Hetzner DNS record through the API.

Inputs: zone name, record name, type, value, TTL, and the API token environment variable.
Outputs: one idempotently managed DNS record in the target Hetzner zone.
