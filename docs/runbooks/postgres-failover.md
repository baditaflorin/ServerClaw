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

```bash
ansible -i inventory/hosts.yml postgres_guests -b -m shell -a 'patronictl -c /etc/patroni/patroni.yml list'
```

Healthy output shows exactly one `Leader` and one `Replica`.

## Verify The VIP Endpoint

```bash
psql "host=database.lv3.org port=5432 dbname=postgres user=ops sslmode=prefer" -Atqc "select not pg_is_in_recovery()"
```

- `t`: the VIP is on the current leader
- `f`: a stale connection or DNS path is being used and needs investigation

## Planned Switchover

Run from either PostgreSQL VM:

```bash
sudo patronictl -c /etc/patroni/patroni.yml switchover --leader postgres-lv3 --candidate postgres-replica-lv3
```

Then verify:

```bash
sudo patronictl -c /etc/patroni/patroni.yml list
psql "host=database.lv3.org port=5432 dbname=postgres user=ops sslmode=prefer" -Atqc "select inet_server_addr(), not pg_is_in_recovery()"
```

## Switch Back

```bash
sudo patronictl -c /etc/patroni/patroni.yml switchover --leader postgres-replica-lv3 --candidate postgres-lv3
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
sudo patronictl -c /etc/patroni/patroni.yml reinit postgres-ha postgres-lv3
```

Use the current leader as the reinit source if Patroni prompts for it.

## Failure Modes

- If both PostgreSQL VMs are up but no leader exists, check the etcd quorum on all three members.
- If Patroni is healthy but the VIP does not move, inspect `keepalived` on both PostgreSQL VMs.
- If services fail to reconnect after failover, verify they are using `database.lv3.org` rather than a pinned node IP.
