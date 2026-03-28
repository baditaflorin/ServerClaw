# hetzner_dns_records

Converges a list of Hetzner DNS records for one zone.
Raw Hetzner payloads are translated into canonical DNS facts before per-record matching or drift logic runs.

Inputs: `hetzner_dns_zone_name`, `hetzner_dns_records`, and `HETZNER_DNS_API_TOKEN`.
Outputs: all desired records created or updated in the target zone.
