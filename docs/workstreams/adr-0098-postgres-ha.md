# Workstream ADR 0098: Postgres High Availability and Automated Failover

- ADR: [ADR 0098](../adr/0098-postgres-high-availability.md)
- Title: Patroni streaming replication with keepalived VIP providing automatic Postgres failover on a second VM (postgres-replica-lv3, VMID 151)
- Status: ready
- Branch: `codex/adr-0098-postgres-ha`
- Worktree: `../proxmox_florin_server-postgres-ha`
- Owner: codex
- Depends On: `adr-0026-postgres-vm`, `adr-0064-health-probes`, `adr-0085-opentofu-vm-lifecycle`, `adr-0096-slo-tracking`, `adr-0097-alerting-routing`
- Conflicts With: none
- Shared Surfaces: `tofu/environments/production/`, `roles/postgres_lv3/`, `inventory/`, `config/service-capability-catalog.json`

## Scope

- add `postgres-replica-lv3` VM to `tofu/environments/production/main.tf` (VMID 151, clone of Debian 13 template)
- write Ansible role `postgres_ha` — installs Patroni, etcd (single-node), and `check_patroni_leader.sh` on both Postgres VMs
- write Ansible role `keepalived_vip` — installs keepalived with VIP `10.10.10.55` on both Postgres VMs
- update Ansible role `postgres_lv3` to deploy via `postgres_ha` on both VMs
- add `postgres-replica-lv3` to `inventory/hosts.yml` and `inventory/host_vars/postgres-replica-lv3.yml`
- update `inventory/group_vars/all.yml` — `postgres_host` var changed to `postgres.internal.lv3` (VIP DNS)
- update all service roles that set Postgres connection strings: `keycloak_postgres`, `mattermost_postgres`, `netbox_postgres`, `openbao_postgres`, `windmill` (and any others in `inventory/group_vars/`)
- add DNS record `postgres.internal.lv3 → 10.10.10.55` to internal DNS config
- add health probes for VIP and replica to `config/health-probe-catalog.json`
- add Patroni Telegraf metrics collection to `roles/guest_observability` — Telegraf HTTP input scraping port 8008 on both VMs
- write Grafana dashboard `config/grafana/dashboards/postgres-ha.json` — leader status, replication lag, WAL position
- write `docs/runbooks/postgres-failover.md` — switchover and failover procedures
- add postgres VIP SLO to `config/slo-catalog.json`

## Non-Goals

- etcd clustering (single-node etcd is intentional; see ADR)
- Connection pooling (PgBouncer) — separate concern for a future ADR
- Multi-master replication (streaming replication is primary → standby only)

## Expected Repo Surfaces

- `tofu/environments/production/main.tf` (patched: VMID 151 added)
- `roles/postgres_ha/`
- `roles/keepalived_vip/`
- `roles/postgres_lv3/` (patched: uses postgres_ha)
- `inventory/hosts.yml` (patched: postgres-replica-lv3 added)
- `inventory/host_vars/postgres-replica-lv3.yml`
- `inventory/group_vars/all.yml` (patched: postgres_host changed to VIP DNS)
- `config/health-probe-catalog.json` (patched)
- `config/slo-catalog.json` (patched)
- `config/grafana/dashboards/postgres-ha.json`
- `docs/runbooks/postgres-failover.md`
- `docs/adr/0098-postgres-high-availability.md`
- `docs/workstreams/adr-0098-postgres-ha.md`

## Expected Live Surfaces

- VMID 151 (`postgres-replica-lv3`) is running at `10.10.10.51`
- `patronictl -c /etc/patroni/patroni.yml list` shows two nodes: one Leader, one Replica
- VIP `10.10.10.55` is pingable and resolves via `postgres.internal.lv3`
- Replication lag < 1 MB (Patroni failover threshold)
- All five dependent services (Keycloak, Windmill, NetBox, OpenBao, Mattermost) are connected to the VIP

## Verification

- `patronictl list` shows both nodes healthy
- `psql -h postgres.internal.lv3 -U postgres -c "SELECT pg_is_in_recovery();"` → `f` (primary)
- Run planned switchover: `patronictl switchover postgres-ha --master postgres-lv3 --candidate postgres-replica-lv3` → verify Keycloak, NetBox, Mattermost remain healthy within 30 seconds
- Switch back to original primary
- Verify replication lag metric appears in the Postgres HA Grafana dashboard

## Merge Criteria

- Both VMs provisioned and Patroni reports both as healthy
- VIP at `10.10.10.55` works and moves on switchover
- All five dependent services connect to VIP (not to bare IP)
- Replication lag Grafana panel shows data
- Postgres VIP SLO defined in `config/slo-catalog.json`
- Planned switchover tested and services recovered within 30 seconds

## Notes For The Next Assistant

- Run `tofu apply` before any Ansible work — the replica VM must exist before Patroni can be configured
- Patroni requires the `replicator` Postgres role to exist on the primary before the replica joins; create it in the `postgres_ha` role's primary-only tasks
- The keepalived `check_patroni_leader.sh` script must use `curl -sf http://localhost:8008/leader` (returns 200 if leader, 503 if not); do not use `patronictl` in the script — it is too slow for keepalived's 2-second check interval
- When updating service connection strings to use the VIP DNS, do a rolling restart (one service at a time) rather than all at once; some services require a full container restart to pick up the new connection string
- After switchover, the old primary becomes a standby; if keepalived is not running on the old primary, the VIP will not move back on the next planned switchover; ensure keepalived starts automatically on both VMs
