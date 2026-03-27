# ADR 0098: Postgres High Availability and Automated Failover

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.103.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
- Date: 2026-03-23

## Context

`postgres-lv3` (VMID 150) is a single-VM PostgreSQL instance that serves as the primary data store for five platform services: Keycloak, Mattermost, NetBox, OpenBao, and Windmill. It is the most consequential single point of failure in the platform:

- If `postgres-lv3` crashes, all five services lose database connectivity simultaneously
- Keycloak loses its session and user store → SSO breaks → every OIDC-protected service becomes inaccessible
- NetBox loses its IPAM data → topology queries fail → the ops portal and agent tools degrade
- Mattermost loses its message store → ChatOps ceases to function during an incident — exactly when it is most needed

The current backup model (ADR 0020) provides point-in-time VM snapshots via PBS, but recovery from a snapshot requires:
1. Noticing the failure (minutes to hours without paging)
2. Manually restoring the VM snapshot from the PBS interface (5–10 minutes)
3. Waiting for Postgres to start and services to reconnect (2–5 minutes)

Even optimistically, this is a 20–30 minute recovery window, all of it manual. For a homelab, this is tolerable occasionally; for a platform that is the operator's primary tool, it is a recurring operational burden.

The platform has the Proxmox infrastructure to provision a second VM (`postgres-replica-lv3`) on the same internal bridge at `10.10.10.51`. The approach chosen must not add operational complexity beyond what one person can maintain.

## Decision

We will provision a second PostgreSQL VM (`postgres-replica-lv3`, VMID 151) and implement **Patroni-managed streaming replication** with automatic failover, keeping `postgres-lv3` as the initial primary and `postgres-replica-lv3` as a hot standby. A virtual IP (VIP) managed by the Ansible `linux_keepalived` role provides a stable connection endpoint that services do not need to reconfigure on failover.

### Topology

```
                    10.10.10.55 (VIP, managed by keepalived)
                         │
           ┌─────────────┴─────────────┐
           │                           │
  10.10.10.50                   10.10.10.51
  postgres-lv3 (primary)    postgres-replica-lv3 (standby)
  VMID 150                   VMID 151
  Patroni leader             Patroni follower
           │                           │
           └────── streaming replication ──────┘
                    WAL shipping (synchronous)
```

Services connect to `database.lv3.org`, which now resolves to `10.10.10.55` (the VIP). On automatic failover, keepalived moves the VIP to the replica without any service reconfiguration.

### Patroni

Patroni is deployed on both PostgreSQL VMs and manages leader election and automatic failover. It requires a distributed consensus store; we use **etcd** rather than Consul or ZooKeeper because etcd is already a reasonable dependency at this scale:

```
etcd is deployed as a three-member quorum on postgres-lv3, postgres-replica-lv3, and monitoring-lv3.
```

This is the minimum quorum that allows Patroni to keep automatic failover working when either PostgreSQL VM is lost. A single-node etcd colocated only with the primary would have failed with the primary and would not have satisfied the automatic failover requirement.

### Patroni configuration extract

```yaml
# patroni.yml (Ansible-templated)
scope: postgres-ha
name: "{{ inventory_hostname }}"

etcd3:
  hosts: 10.10.10.50:2379,10.10.10.51:2379,10.10.10.40:2379

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 10
    maximum_lag_on_failover: 1048576  # 1 MB — standby cannot be more than 1 MB behind

postgresql:
  listen: "0.0.0.0:5432"
  connect_address: "{{ ansible_host }}:5432"
  data_dir: /var/lib/postgresql/17/main
  pg_hba:
    - host replication replicator 10.10.10.0/24 scram-sha-256
    - host all all 10.10.10.0/24 scram-sha-256
  parameters:
    synchronous_commit: "on"
    synchronous_standby_names: "*"
    wal_level: replica
    max_wal_senders: 5
    max_replication_slots: 5
```

`synchronous_commit: on` with `synchronous_standby_names: "*"` means Postgres will not acknowledge a write until the replica has received and flushed the WAL. This ensures zero data loss on planned failover (RPO = 0 transactions). The trade-off is a small write latency increase (~1–2ms for local network WAL sync).

### keepalived VIP

```
# /etc/keepalived/keepalived.conf (Ansible-templated on both nodes)
vrrp_instance postgres_vip {
    state {{ 'MASTER' if inventory_hostname == 'postgres-lv3' else 'BACKUP' }}
    interface eth0
    virtual_router_id 51
    priority {{ '100' if inventory_hostname == 'postgres-lv3' else '90' }}
    advert_int 1
    virtual_ipaddress {
        10.10.10.55/24
    }
    track_script {
        chk_postgres
    }
}

vrrp_script chk_postgres {
    script "/usr/local/bin/check_patroni_leader.sh"
    interval 2
    fall 2
    rise 2
}
```

The `check_patroni_leader.sh` script returns 0 if the local node is the Patroni leader, 1 otherwise. keepalived moves the VIP to the node that is currently the Patroni leader, ensuring VIP and Patroni leadership are always co-located.

### Service connection strings

All services are updated to connect to the VIP DNS name `database.lv3.org` rather than the bare node IP:

```ini
# Example: Keycloak connection string (Ansible-templated)
KC_DB_URL=jdbc:postgresql://database.lv3.org:5432/keycloak
```

This change is applied to: Keycloak, Mattermost, NetBox, OpenBao, Windmill.

### OpenTofu provisioning

`postgres-replica-lv3` is added to `tofu/environments/production/main.tf` as a new VM resource cloned from the Debian 13 cloud template, with the same sizing as `postgres-lv3` (8 GB RAM, 4 vCPU, 80 GB disk).

### Ansible roles

- New role `postgres_ha` — installs and configures Patroni + etcd on the primary and replica
- New role `linux_keepalived` — manages the keepalived configuration and VIP
- New role `etcd_cluster_member` — manages the three-member etcd quorum used by Patroni
- The `postgres-vm` playbook is updated to deploy `postgres_ha` on both VMs

### Failover procedure

**Automatic failover** (primary VM crash or Postgres process death):
1. Patroni on the replica detects the primary is unreachable (within `ttl: 30` seconds)
2. Patroni promotes the replica to leader
3. keepalived detects the leadership change via `check_patroni_leader.sh`
4. keepalived moves the VIP to the new leader within ~2 seconds
5. Services with connection retry logic (all five) reconnect to the VIP automatically
6. Total unplanned failover time: 30–45 seconds

**Planned failover** (maintenance, upgrade):
```bash
patronictl -c /etc/patroni/patroni.yml switchover postgres-ha --master postgres-lv3 --candidate postgres-replica-lv3
```
Switchover completes in < 5 seconds with zero transaction loss.

### Monitoring

- Patroni exposes a REST API at port 8008; a Telegraf HTTP input scrapes `/patroni` on both nodes and sends leader status, replication lag, and WAL position to Grafana
- A Grafana alert fires if replication lag exceeds 10 MB (`maximum_lag_on_failover` is 1 MB; 10 MB triggers a warning before the failover threshold is hit)
- An SLO (ADR 0096) is defined for Postgres VIP availability: 99.9% over 30 days

## Consequences

**Positive**
- The most consequential SPOF in the platform is eliminated; planned and unplanned failover is automatic
- Planned VM maintenance (patching, resizing) can now be performed on one node at a time without any service downtime
- RPO = 0 transactions for planned failover; for unplanned failover, the maximum loss is the transactions in-flight at the moment of crash (synchronous commit limits this to zero for committed transactions)
- RTO = 30–45 seconds for automatic failover, < 5 seconds for planned switchover

**Negative / Trade-offs**
- A second Postgres VM (`postgres-replica-lv3`) requires 8 GB RAM and 80 GB disk — a significant resource commitment on a single-host Proxmox node
- Patroni adds configuration complexity; the `patronictl` command must be used for Postgres maintenance instead of `pg_ctl`
- A third etcd quorum member now runs on `monitoring-lv3`, which expands the operational footprint beyond the original two PostgreSQL VMs
- `synchronous_commit: on` adds ~1–2ms latency to all Postgres writes; acceptable for the application workloads in this platform

## Alternatives Considered

- **Manual restore from PBS snapshot**: current approach; 20–30 min RTO, all manual; insufficient for a platform that is a primary operator tool
- **Pgpool-II**: query router + HA; complex configuration; adds a third moving part; Patroni + keepalived achieves the same failover outcome with less complexity
- **Postgres logical replication with pgBouncer**: supports heterogeneous versions but does not support automatic failover without additional tooling; streaming replication is the correct primitive
- **Accept the SPOF**: for a personal homelab, one could argue a single Postgres VM is fine; but the platform is now the operator's primary tool for all other operations — losing it during an incident would be a significant problem

## Related ADRs

- ADR 0020: Storage and backup model (replica is added to backup scope)
- ADR 0026: Dedicated PostgreSQL VM baseline (this ADR extends it)
- ADR 0064: Health probe contracts (VIP health probe added)
- ADR 0085: OpenTofu VM lifecycle (replica provisioned via OpenTofu)
- ADR 0096: SLO definitions (Postgres VIP SLO added)
- ADR 0097: Alerting routing (replication lag alert and VIP down alert)
- ADR 0100: Disaster recovery playbook (failover procedure documented there)
