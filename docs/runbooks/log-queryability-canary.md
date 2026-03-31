# Log Queryability Canary

## Purpose

This runbook covers the repo-managed Loki Canary runtime introduced by ADR 0250.

Use it when the platform needs proof that the central Loki path can still:

- accept new canary log entries
- return those entries over the websocket tail path
- return those entries again through direct LogQL queries

## Alert Conditions

- `max(up{job="loki-canary"}) == 0`
- `increase(loki_canary_missing_entries_total[15m]) > 0`
- `increase(loki_canary_spot_check_missing_entries_total[15m]) > 0`
- `increase(loki_canary_websocket_missing_entries_total[15m]) > 0`
- `abs(loki_canary_metric_test_deviation) > 4`

## Immediate Steps

1. Confirm the monitoring stack is still healthy on `monitoring-lv3`.
2. Check the Loki Canary service status and recent logs.
3. Verify Prometheus can still scrape the canary target.
4. Query Loki directly for the canary stream before changing anything.

## Diagnosis

Check the service itself:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o 'ProxyCommand=ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p' ops@10.10.10.40 'systemctl status loki-canary --no-pager && journalctl -u loki-canary -n 100 --no-pager'
```

Check the exported metrics:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o 'ProxyCommand=ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p' ops@10.10.10.40 'curl -fsS http://127.0.0.1:3500/metrics | grep "^loki_canary_" | sed -n "1,40p"'
```

Check the Prometheus scrape result:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o 'ProxyCommand=ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p' ops@10.10.10.40 'curl -fsS --get --data-urlencode '\''query=up{job="loki-canary"}'\'' http://127.0.0.1:9090/api/v1/query | jq -c .data.result'
```

Check whether the canary stream is still queryable in Loki:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o 'ProxyCommand=ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p' ops@10.10.10.40 'start=$(date -u -d "15 minutes ago" +%s000000000); end=$(date -u +%s000000000); curl -fsSG --data-urlencode "query={name=\"loki-canary\",stream=\"stdout\"}" --data-urlencode limit=5 --data-urlencode start=$start --data-urlencode end=$end http://127.0.0.1:3100/loki/api/v1/query_range | jq -c .data.result'
```

## Resolution

1. If the service unit or rendered arguments drifted, replay the managed Grafana service bundle:

```bash
BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
ALLOW_IN_PLACE_MUTATION=true \
make live-apply-service service=grafana env=production EXTRA_ARGS='-e bypass_promotion=true'
```

Because `monitoring-lv3` is still governed by ADR 0191 immutable guest replacement, this replay uses the narrow documented in-place mutation exception for reversible monitoring-stack changes.

2. If `loki-canary` is healthy but Loki queries still fail, inspect `loki`, `lv3-prometheus`, and `grafana-server` logs on `monitoring-lv3` before restarting anything else.
3. If the problem is only websocket lag while direct queries still pass, treat it as a degraded monitoring-path incident and keep the warning alert open until the counters stop increasing.

## Escalation

Escalate after 15 minutes if:

- the canary target stays down after a managed replay
- `missing_entries_total` or `spot_check_missing_entries_total` keeps increasing
- Loki itself is no longer healthy on `monitoring-lv3`

## Post-Incident

Record whether the failure was:

- canary process down
- Prometheus scrape failure
- Loki ingest failure
- Loki query-path failure
- websocket-only degradation
