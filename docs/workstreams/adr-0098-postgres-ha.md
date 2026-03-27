# Workstream ADR 0098: Postgres High Availability and Automated Failover

- ADR: [ADR 0098](../adr/0098-postgres-high-availability.md)
- Title: Patroni streaming replication with keepalived VIP providing automatic Postgres failover on a second VM (postgres-replica-lv3, VMID 151)
- Status: merged
- Branch: `codex/adr-0098-postgres-ha`
- Worktree: `../proxmox_florin_server-postgres-ha`
- Owner: codex
- Depends On: `adr-0026-postgres-vm`, `adr-0064-health-probes`, `adr-0085-opentofu-vm-lifecycle`, `adr-0096-slo-tracking`, `adr-0097-alerting-routing`
- Conflicts With: none
- Shared Surfaces: `tofu/environments/production/`, `inventory/`, `inventory/group_vars/platform.yml`, `collections/ansible_collections/lv3/platform/roles/postgres_ha/`, `config/service-capability-catalog.json`

## Scope

- add `postgres-replica-lv3` VM to `tofu/environments/production/main.tf` (VMID 151, clone of Debian 13 template)
- write Ansible role `postgres_ha` — installs Patroni, manages the PostgreSQL HA configuration, and ships Patroni metrics from both Postgres VMs
- write Ansible role `linux_keepalived` — installs keepalived with VIP `10.10.10.55` on both Postgres VMs
- write Ansible role `etcd_cluster_member` — provides the three-member DCS quorum on `postgres-lv3`, `postgres-replica-lv3`, and `monitoring-lv3`
- add `postgres-replica-lv3` to `inventory/hosts.yml` and the canonical guest source-of-truth files
- update all service roles that set Postgres connection strings to use `database.lv3.org`
- move the existing `database.lv3.org` DNS target to the HA VIP `10.10.10.55`
- update health probes, Uptime Kuma, and Grafana dashboards to reflect the VIP and Patroni role metrics
- write `docs/runbooks/postgres-failover.md` — switchover and failover procedures

## Non-Goals

- SLO automation for the Postgres VIP
- Connection pooling (PgBouncer) — separate concern for a future ADR
- Multi-master replication (streaming replication is primary → standby only)

## Expected Repo Surfaces

- `tofu/environments/production/main.tf` (patched: VMID 151 added)
- `collections/ansible_collections/lv3/platform/roles/postgres_ha/`
- `collections/ansible_collections/lv3/platform/roles/linux_keepalived/`
- `collections/ansible_collections/lv3/platform/roles/etcd_cluster_member/`
- `inventory/hosts.yml` (patched: postgres-replica-lv3 added)
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `config/health-probe-catalog.json` (patched)
- `config/uptime-kuma/monitors.json` (patched)
- `collections/ansible_collections/lv3/platform/roles/monitoring_vm/templates/lv3-platform-overview.json.j2`
- `collections/ansible_collections/lv3/platform/roles/monitoring_vm/templates/lv3-vm-detail.json.j2`
- `docs/runbooks/postgres-failover.md`
- `docs/adr/0098-postgres-high-availability.md`
- `docs/workstreams/adr-0098-postgres-ha.md`

## Expected Live Surfaces

- VMID 151 (`postgres-replica-lv3`) is running at `10.10.10.51`
- `patronictl -c /etc/patroni/patroni.yml list` shows two nodes: one Leader, one Replica
- VIP `10.10.10.55` is reachable through `database.lv3.org`
- Replication lag < 1 MB (Patroni failover threshold)
- All five dependent services (Keycloak, Windmill, NetBox, OpenBao, Mattermost) are connected to the VIP

## Verification

- `patronictl list` shows both nodes healthy
- `psql -h database.lv3.org -U postgres -c "SELECT pg_is_in_recovery();"` → `f` (primary)
- Run planned switchover: `patronictl switchover postgres-ha --master postgres-lv3 --candidate postgres-replica-lv3` → verify Keycloak, NetBox, Mattermost remain healthy within 30 seconds
- Switch back to original primary
- Verify replication lag metric appears in the Postgres HA Grafana dashboard

## Merge Criteria

- Both VMs provisioned and Patroni reports both as healthy
- VIP at `10.10.10.55` works and moves on switchover
- All five dependent services connect to VIP (not to bare IP)
- Replication lag Grafana panel shows data
- Planned switchover tested and services recovered within 30 seconds

## Notes For The Next Assistant

- Repo implementation is merged; the remaining work is live rollout from `main`
- As of `2026-03-27`, production no longer has VMID `151` in `qm list`, so active production host targeting must not include `postgres-replica-lv3` until ADR 0098 is actually live-applied again.
- Run `tofu apply` before any Ansible work — the replica VM must exist before Patroni can be configured
- The keepalived `check_patroni_leader.sh` script must use `curl -sf http://localhost:8008/leader` (returns 200 if leader, 503 if not); do not use `patronictl` in the script — it is too slow for keepalived's 2-second check interval
- When updating service connection strings to use the VIP DNS, do a rolling restart (one service at a time) rather than all at once; some services require a full container restart to pick up the new connection string
- After switchover, the old primary becomes a standby; if keepalived is not running on the old primary, the VIP will not move back on the next planned switchover; ensure keepalived starts automatically on both VMs
