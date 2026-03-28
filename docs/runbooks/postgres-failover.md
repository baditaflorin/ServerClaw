# PostgreSQL Failover Runbook

## Purpose

Operate the LV3 Patroni-managed PostgreSQL HA pair behind the `database.lv3.org` VIP.

## Topology

- `postgres-lv3` at `10.10.10.50`
- `postgres-replica-lv3` at `10.10.10.51`
- VIP `10.10.10.55` exposed as `database.lv3.org`
- Patroni REST API on `:8008`
- etcd quorum members on `postgres-lv3`, `postgres-replica-lv3`, and `monitoring-lv3`

## Check Cluster State

The live unit file now points Patroni at `/etc/patroni/config.yml`, but the current 2026-03-27 evidence on production shows that file is absent and the service is inactive. Confirm the current runtime first:

```bash
ssh -i .local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand="ssh -i .local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p" \
  ops@10.10.10.50 \
  'hostname && sudo systemctl is-active patroni keepalived && sudo ls -l /etc/patroni'
```

If Patroni is healthy and `/etc/patroni/config.yml` exists, list the cluster from either PostgreSQL VM:

```bash
ssh -i .local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand="ssh -i .local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p" \
  ops@10.10.10.50 \
  'sudo patronictl -c /etc/patroni/config.yml list'
```

Healthy output shows exactly one `Leader` and one `Replica`.

## Verify The VIP Endpoint

```bash
ssh -i .local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 \
  'timeout 5 bash -lc "echo > /dev/tcp/10.10.10.55/5432" && echo vip-open || echo vip-closed'
```

- `vip-open`: the VIP is reachable from the Proxmox host path
- `vip-closed`: the VIP is not currently published and the rehearsal must stop until the HA path is restored

## Planned Switchover

Only continue when Patroni is active on both PostgreSQL VMs, the replica VM exists, and the VIP path is reachable. Run from either PostgreSQL VM:

```bash
sudo patronictl -c /etc/patroni/config.yml switchover --leader postgres-lv3 --candidate postgres-replica-lv3
```

Then verify:

```bash
sudo patronictl -c /etc/patroni/config.yml list
psql "host=10.10.10.55 port=5432 dbname=postgres user=ops sslmode=prefer" -Atqc "select inet_server_addr(), not pg_is_in_recovery()"
```

## Switch Back

```bash
sudo patronictl -c /etc/patroni/config.yml switchover --leader postgres-replica-lv3 --candidate postgres-lv3
```

## Unplanned Failover Checks

1. Confirm Patroni elected a new leader.
2. Confirm `database.lv3.org:5432` accepts connections.
3. Confirm dependent services are healthy:
   - Keycloak discovery
   - NetBox private UI
   - Mattermost private UI
   - Windmill private API
   - OpenBao health and database credential issuance
4. Review Grafana panels for `postgres_ha` leader state and replication lag.

## Rejoin A Failed Former Primary

After the failed node returns:

```bash
sudo patronictl -c /etc/patroni/config.yml reinit postgres-ha postgres-lv3
```

Use the current leader as the reinit source if Patroni prompts for it.

## Failure Modes

- If both PostgreSQL VMs are up but no leader exists, check the etcd quorum on all three members.
- If Patroni is healthy but the VIP does not move, inspect `keepalived` on both PostgreSQL VMs.
- If services fail to reconnect after failover, verify they are using `database.lv3.org` rather than a pinned node IP.

## Rehearsal Evidence

Every planned failover rehearsal for ADR 0188 must publish:

- trigger and target environment
- duration and observed RTO
- data-loss or lag observation
- dependency health verification results
- rollback or failback result

Store the evidence in a structured live-apply receipt when the run is part of a governed change, or in a branch-local evidence note referenced from `config/service-redundancy-catalog.json` when the exercise fails before the switchover can begin.
