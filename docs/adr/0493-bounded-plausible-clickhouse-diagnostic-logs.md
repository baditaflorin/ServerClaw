# ADR 0493: Bound Plausible ClickHouse diagnostic log storage

- Status: Accepted
- Implementation Status: Implemented and verified in production
- Implemented In Repo Version: pending
- Implemented In Platform Version: 0.178.226
- Implemented On: 2026-10-07
- Date: 2026-10-07

## Context

Plausible's ClickHouse system diagnostic tables grew to about 85 GiB on the
runtime VM, while the analytics event store was only a few hundred MiB. The
largest contributors were text and trace logs, which do not provide long-term
customer analytics value. The unbounded default allowed these diagnostic tables
to exhaust the VM's SSD-backed filesystem and disrupt unrelated services.

## Decision

Set a one-day TTL on Plausible ClickHouse's persistent diagnostic system log
tables through the repository-managed ClickHouse XML configuration. Cover text,
trace, metric, asynchronous metric, part, error, background scheduler,
processor profile, query, query metric, and asynchronous insert logs. Keep the
diagnostic history useful for recent troubleshooting while bounding its age.
Limit the structured `text_log` table to warning-level messages, since its
default without a configured level records every message.

Keep analytics event retention unchanged at 365 days. This policy applies only
to `system` diagnostic tables, not Plausible's `events_v2` data. ClickHouse
applies TTL during part merges, so the configured duration is an age limit for
eligible data rather than a precise deletion deadline.

## Consequences

- Future Plausible converges restore the diagnostic TTL after container
  recreation or host recovery.
- Recent diagnostic logs remain available for investigation; older history is
  discarded automatically as parts merge.
- Existing oversized legacy system tables still require a one-time cleanup;
  this configuration does not replace historical cleanup already performed.
- Applying a changed ClickHouse config currently recreates the Plausible
  Compose project and its four live containers, requiring a brief analytics
  interruption.
- Rollback is a config revert followed by the same Plausible converge. Rollback
  cannot restore diagnostic rows already deleted by TTL.
