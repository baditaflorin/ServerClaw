# hetzner_dns_records

Converges a list of Hetzner DNS records for one zone.
Raw Hetzner payloads are translated into canonical DNS facts before per-record matching or drift logic runs.

Inputs: `hetzner_dns_zone_name`, `hetzner_dns_records`, and `HETZNER_DNS_API_TOKEN`.
Outputs: all desired records created or updated in the target zone.

## Brownout manual-fallback mode (ADR 0430 PR 3)

Hetzner announced the DNS-Console write API brownout leading to full
shutdown on 2026-05-20. During the brownout, writes silently no-op.

Set `hetzner_dns_brownout_manual_fallback: true` to:

- Skip all create / update / delete API calls for the zone.
- Run the reads normally so drift detection remains accurate.
- Print a consolidated list of records that need to be published manually
  via https://dns.hetzner.com/zones.
- Exit the role successfully so the rest of the converge chain can proceed.

After the brownout lifts (or after switching to a successor DNS provider),
flip the variable back to `false` and the next converge will reconcile
any drift automatically.
