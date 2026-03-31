# PostgreSQL Audit Runbook

## Purpose

This runbook is the operational reference for ADR 0303 on `postgres-lv3`.

It covers:

- the managed `pgaudit` enablement on the production PostgreSQL primary
- the approved-role and sensitive-table catalogs that shape audit scope
- the Alloy parsing pipeline that turns PostgreSQL log lines into Loki streams and Prometheus counters
- the Alertmanager relay that publishes unknown-role connection alerts to `platform.security.pgaudit_unknown_role`

## Canonical Sources

- ADR: [docs/adr/0303-pgaudit-for-postgresql-query-and-privilege-change-audit-logging.md](../adr/0303-pgaudit-for-postgresql-query-and-privilege-change-audit-logging.md)
- PostgreSQL role: [roles/postgres_vm](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/postgres_vm)
- guest log shipping role: [roles/loki_log_agent](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/loki_log_agent)
- monitoring role: [roles/monitoring_vm](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/monitoring_vm)
- Alertmanager runtime role: [roles/alertmanager_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/alertmanager_runtime)
- approved login roles: [config/pgaudit/approved-roles.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/pgaudit/approved-roles.yaml)
- sensitive tables: [config/pgaudit/sensitive-tables.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/pgaudit/sensitive-tables.yaml)
- alert rules: [config/alertmanager/rules/platform.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/alertmanager/rules/platform.yml)
- event taxonomy: [config/event-taxonomy.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/event-taxonomy.yaml)

## What The Automation Configures

- `shared_preload_libraries = 'pgaudit'` on the live PostgreSQL 17 cluster
- `pgaudit.log = 'ddl,role'`
- `log_connections = on` and `log_disconnections = on`
- a dedicated `pgaudit_auditor` role plus per-object grants for the sensitive `windmill` and `n8n` tables
- the `pgaudit` extension in every writable database
- a dedicated Alloy file source for PostgreSQL logs with metrics:
  - `postgres_audit_events_total`
  - `postgres_connection_authorized_total`
  - `postgres_unknown_connection_events_total`
- Prometheus scrape coverage for the Alloy metrics endpoint on `postgres-lv3:12345`
- Alertmanager routing for `PostgresUnknownRoleConnection` into ntfy, Mattermost, and the local pgaudit relay
- a local relay on `monitoring-lv3` that publishes `platform.security.pgaudit_unknown_role` over NATS

## Converge

Replay the PostgreSQL changes:

```bash
make converge-postgres-vm
```

Replay the monitoring and alerting path:

```bash
make converge-monitoring
```

The first `pgaudit` enablement requires a PostgreSQL restart. Coordinate that replay as a maintenance-window change when the live primary still lacks `shared_preload_libraries = 'pgaudit'`.

## Verify Runtime State

Check the PostgreSQL cluster settings on `postgres-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o 'ProxyCommand=ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ops@100.64.0.1 -W %h:%p' ops@10.10.10.50 "sudo -u postgres psql -Atqc \"SHOW shared_preload_libraries; SHOW pgaudit.log; SHOW log_connections; SHOW log_disconnections;\""
```

Expected values:

- `shared_preload_libraries` includes `pgaudit`
- `pgaudit.log` is `ddl,role`
- both `log_connections` and `log_disconnections` are `on`

Check the guest-local Alloy metrics endpoint:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o 'ProxyCommand=ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ops@100.64.0.1 -W %h:%p' ops@10.10.10.50 "curl -fsS http://127.0.0.1:12345/metrics | rg 'postgres_(audit_events|connection_authorized|unknown_connection_events)_total'"
```

Those metric families are event-driven. After an Alloy restart or a
`guest-log-shipping` replay, seed one deterministic ROLE audit event before
treating a missing metric family as a failure:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o 'ProxyCommand=ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ops@100.64.0.1 -W %h:%p' ops@10.10.10.50 "sudo -u postgres psql -v ON_ERROR_STOP=1 postgres -c \"DROP ROLE IF EXISTS guest_log_shipping_metrics_probe; CREATE ROLE guest_log_shipping_metrics_probe NOLOGIN; DROP ROLE guest_log_shipping_metrics_probe;\""
```

Check the monitoring-side scrape and relay health:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 "curl -fsS --get --data-urlencode 'query=up{job=\"postgres-audit-alloy\"}' http://127.0.0.1:9090/api/v1/query | jq -c .data.result && curl -fsS http://127.0.0.1:19094/healthz"
```

## Query Loki

Recent pgaudit lines:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'start=$(date -u -d "30 minutes ago" +%s000000000); end=$(date -u +%s000000000); curl -fsSG --data-urlencode "query={job=\"postgres-audit\",host=\"postgres-lv3\"} |~ \"AUDIT:\"" --data-urlencode limit=20 --data-urlencode start=$start --data-urlencode end=$end http://127.0.0.1:3100/loki/api/v1/query_range | jq -c .data.result'
```

Unknown-role connection lines:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'start=$(date -u -d "30 minutes ago" +%s000000000); end=$(date -u +%s000000000); curl -fsSG --data-urlencode "query={job=\"postgres-audit\",host=\"postgres-lv3\"} |~ \"connection authorized:\"" --data-urlencode limit=20 --data-urlencode start=$start --data-urlencode end=$end http://127.0.0.1:3100/loki/api/v1/query_range | jq -c .data.result'
```

## Verify The Alert And Event Path

1. Create a temporary PostgreSQL login role outside [config/pgaudit/approved-roles.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/pgaudit/approved-roles.yaml).
2. Grant it a temporary `CONNECT` path to a disposable database such as `postgres`.
3. Open one connection.
4. Confirm:
   - `postgres_unknown_connection_events_total` increases
   - `PostgresUnknownRoleConnection` appears in Prometheus and Alertmanager
   - the ntfy critical path receives the alert
   - a NATS consumer can read one `platform.security.pgaudit_unknown_role` envelope
5. Drop the temporary login role and remove any temporary grant.

If Alertmanager is already tracking another firing `PostgresUnknownRoleConnection`
group for the same `alertname` and `service`, allow up to the configured
`group_interval` (`5m`) for the relay webhook to publish the next NATS event.
Prometheus can show the new role-specific alert immediately while the relay POST
appears on the next grouped notification boundary.

Suggested verification query on `monitoring-lv3`:

```bash
curl -fsS --get --data-urlencode 'query=ALERTS{alertname="PostgresUnknownRoleConnection"}' http://127.0.0.1:9090/api/v1/query | jq -c .data.result
```

Suggested NATS smoke verification from the controller:

```bash
uv run --with nats-py --with pyyaml python - <<'PY'
import asyncio, json, pathlib, sys
repo = pathlib.Path("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server")
sys.path.insert(0, str(repo / "scripts"))
from drift_lib import publish_nats_events  # noqa: E402
print("Use a direct NATS subscriber or stream inspection to confirm the relay-published event on platform.security.pgaudit_unknown_role.")
PY
```

## Troubleshooting

- If `SHOW shared_preload_libraries` does not include `pgaudit`, inspect `/etc/postgresql/17/main/conf.d/90-lv3-postgres.conf` and the last PostgreSQL restart on `postgres-lv3`.
- If the metrics endpoint is down, inspect `/etc/default/alloy`, `/etc/alloy/config.alloy`, and `journalctl -u alloy`.
- If the endpoint is up but the PostgreSQL metric families are missing right
  after a replay, generate the deterministic probe role above so Alloy ingests a
  fresh ROLE audit line and a fresh connection-authorized line before retrying
  the scrape check.
- If Prometheus is not scraping the target, confirm `monitoring-lv3` can reach `postgres-lv3:12345` and that the guest firewall still permits `monitoring-lv3`.
- If alerts fire but no NATS event appears, inspect `systemctl status pgaudit-alert-relay` and `journalctl -u pgaudit-alert-relay` on `monitoring-lv3`, then allow for the current Alertmanager `group_interval` before treating the missing event as a relay failure.
- If Alloy sees connection lines but the unknown-role counter stays flat, compare the live role against [config/pgaudit/approved-roles.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/pgaudit/approved-roles.yaml) and make sure the role name matches exactly.
