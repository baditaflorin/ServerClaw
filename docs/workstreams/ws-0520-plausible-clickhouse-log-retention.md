# Workstream ws-0520: Bound Plausible ClickHouse diagnostic logs

## Goal

Prevent ClickHouse diagnostic tables from consuming unbounded disk while
preserving Plausible analytics events and a short troubleshooting window.

## Scope

- Apply a one-day TTL to the persistent Plausible ClickHouse system log tables.
- Keep the structured ClickHouse text log at warning level to reduce its write rate.
- Keep the analytics event store's 365-day retention unchanged.
- Add a regression check and document deploy impact and rollback.
- Merge through the private-source pull request path, then converge Plausible
  and verify health and table TTL metadata.

## Preflight

The production target is the Plausible stack on `docker-runtime` VM 120. Its
three containers are `plausible`, `plausible-db`, and `plausible-events-db`;
the Plausible readiness endpoint and event ingestion depend on this stack.
The live project currently has four containers: `plausible`, `plausible-db`,
`plausible-events-db`, and `plausible-openbao-agent`. The convergence currently
force-recreates the project, so expect a brief dashboard and tracker
interruption. No analytics rows are deleted by changing the config. Rollback
reverts the managed XML and reruns the converge; diagnostic rows already
expired by TTL cannot be restored. Confirm container count, current health,
and any active event load immediately before applying.

## Verification

- Run `make syntax-check-plausible` and `pytest tests/test_plausible_playbook.py`.
- After merge, run the documented Plausible converge.
- Verify all configured `system` log tables report a one-day TTL, Plausible
  health returns HTTP 200, tracker JavaScript returns HTTP 200, and the
  analytics event table remains intact.

## Live application — 2026-10-07

Merged as PR [#275](https://github.com/baditaflorin/platform_server/pull/275),
commit `490b74499da3cb800ed1b5994af848346593bfb4`, then applied to production
on docker-runtime VM120. The runtime-only scoped converge skipped DNS and NGINX.
Ansible recap: 246 successful tasks, 2 changed, 0 unreachable, 0 failed.

Post-apply evidence:

- All 11 configured ClickHouse diagnostic tables report the one-day TTL.
- Plausible reports `sessions`, `postgres`, `clickhouse`, and `sites_cache` as
  healthy locally and through `https://analytics.example.org/api/health`.
- `https://analytics.example.org/js/script.js` returns HTTP 200.
- The ClickHouse `events_v2` table contains 1,257 rows (71.46 KiB); the
  converge's synthetic pageview was observed. The diagnostic retention config
  does not alter the analytics-event retention policy.
- The runtime root filesystem has 123 GiB free (50% used).

The live cleanup removed the historical diagnostic buildup before this managed
default was deployed. See the [apply receipt](../../receipts/live-applies/ws-0520-plausible-clickhouse-log-retention-apply-receipt.json)
for the exact target and verification record.
