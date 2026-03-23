# postgres_ha

Converge the Patroni-managed PostgreSQL HA pair for LV3.

Inputs: shared HA topology from `hostvars['proxmox_florin'].postgres_ha`, local password artifact paths, and the shared guest-observability inputs.
Outputs: Patroni-managed PostgreSQL on `postgres-lv3` and `postgres-replica-lv3`, keepalived VIP handling, Telegraf HA metrics, and a stable writable leader endpoint.
