# Workstream ws-0359-live-apply: ADR 0359 Declarative PostgreSQL Client Registry

- ADR: [ADR 0359](../adr/0359-declarative-postgres-client-registry.md)
- Title: verify and live-apply the declarative PostgreSQL client registry from the latest `origin/main`
- Status: in progress
- Included In Repo Version: `0.178.129`
- Latest Verified Base: `origin/main@bbdb0f7008db4bac81c8cc30a287e728b83790a1`
- Branch: `codex/ws-0359-main-merge-r2`
- Worktree: `.worktrees/ws-0359-main-merge-r2`
- Owner: codex

## Scope

- confirm the current `origin/main` still contains the ADR 0359 implementation surfaces
- provision any missing PostgreSQL HA guests required by the governed `postgres-vm` replay
- run the exact-main live apply from this clean worktree and capture receipts
- update ADR, workstream, and release metadata only after the platform replay is verified

## Current Starting Point

- `origin/main` currently points to `bbdb0f7008db4bac81c8cc30a287e728b83790a1` and `VERSION` is `0.178.129`
- the implementation exists in code on this base:
  - `inventory/group_vars/platform_postgres.yml` defines `platform_postgres_clients`
  - `inventory/group_vars/postgres_guests.yml` derives guest source allowlists from the registry
  - the shared `lv3.platform.postgres_client` role is present and per-service postgres roles call it
- the authoritative blocker from the prior exact-main replay is still expected until disproven:
  `postgres-apps`, `postgres-data`, and `postgres-replica` were declared in inventory but absent from Proxmox (`qm status` missing for VMIDs `151`, `152`, and `154`)

## Verification To Date

- On 2026-04-13, the focused role regression slice
  `python3 -m pytest -q tests/test_proxmox_guests_role.py`
  passed with `3 passed in 0.13s` after adding live template fallback for `lv3.platform.proxmox_guests`.
- On 2026-04-13, the narrow guest provisioning replay
  provisioned `postgres-replica`, `postgres-apps`, and `postgres-data` from the live
  base template `9000` after resolving the missing `lv3-postgres-host` template `9002`
  through its declared `source_template`; evidence is
  `receipts/live-applies/evidence/2026-04-13-ws-0359-provision-ha-guests-r2-0.178.129.txt`.
- On 2026-04-13, Proxmox reported VMIDs `151`, `152`, and `154` as `running`, with
  evidence at `receipts/live-applies/evidence/2026-04-13-ws-0359-proxmox-qm-status-r2-0.178.129.txt`.
- On 2026-04-13, Ansible could reach `postgres-replica`, `postgres-apps`, and
  `postgres-data` through the `proxmox_host_jump` path; evidence is
  `receipts/live-applies/evidence/2026-04-13-ws-0359-postgres-ha-ping-r1-0.178.129.txt`.

## Plan

1. Recreate workstream ownership on the latest exact-main branch so repo automation can validate the session honestly.
2. Provision the missing PostgreSQL HA guests with a narrow `proxmox_guests_active` target.
3. Run `make live-apply-service service=postgres-vm env=production` from this worktree and verify `pg_hba.conf`, firewall reachability, and representative `psql` connectivity.
4. Update ADR/workstream/release truth, run the repo validation and push gates, then fast-forward the final result to `origin/main`.
