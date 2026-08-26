# `network_policy` Rule Provenance

See ADR 0489. Each entry in `network_policy.guests.<name>.allowed_inbound` (in
`inventory/host_vars/proxmox-host.yml`) may carry an optional `provenance` block
alongside the existing (universal, freeform) `description` field:

```yaml
- source: monitoring
  protocol: tcp
  ports: [9100]
  description: Prometheus node_exporter metrics scrape access
  provenance:
    owner: operator@example.com     # who to ask if this rule looks wrong
    added_on: "2026-08-26"            # ISO date the rule was declared here
    reconciled_from_live: true        # true if discovered live (drift) before
                                       # being declared here; false/omitted for
                                       # rules declared before ever being applied
    workstream: null                  # optional ADR/workstream id this rule
                                       # was introduced for
```

## Rules

- `provenance` is **optional**. Do not add it to existing rules as a migration —
  backfill organically, the same convention `services-registry`'s `owner` field
  uses (see its schema description and `fleet-runner audit` precedent).
- Neither `nftables.conf.j2` nor `vm.fw.j2` reads `provenance` (or `description`)
  — it is metadata for humans and for `scripts/firewall_drift.py`'s `explain`
  query, not part of the rendered firewall config. Adding or editing it never
  changes what gets applied to a host.
- `owner` should be an email or a name resolvable the same way
  `service-capability-catalog.json`'s (informal) ownership conventions are —
  this repo does not yet have a single canonical identity field for this; match
  `receipts/gate-bypasses/*.json`'s `owner` (an email) if in doubt.
- `reconciled_from_live: true` is a meaningful signal, not decoration: it tells
  `scripts/firewall_drift.py` (and a future reader) that this rule's history
  started as an out-of-band live change, which is worth knowing when auditing
  how rules get introduced on this fleet.
