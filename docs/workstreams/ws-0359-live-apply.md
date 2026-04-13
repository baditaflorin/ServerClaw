# Workstream ws-0359-live-apply: ADR 0359 Declarative PostgreSQL Client Registry

- ADR: [ADR 0359](../adr/0359-declarative-postgres-client-registry.md)
- Title: verify and live-apply the declarative PostgreSQL client registry from the latest `origin/main`
- Status: live applied
- Included In Repo Version: `0.178.131`
- Latest Realistic Apply Base: `origin/main@bbdb0f7008db4bac81c8cc30a287e728b83790a1` (`VERSION=0.178.129`)
- Latest Reachable origin/main: `origin/main@063e88c0fe49c278cbfe231a345eaebb145ec404` (`VERSION=0.178.130`)
- Branch: `codex/ws-0359-main-merge-r2`
- Worktree: `.worktrees/ws-0359-main-merge-r2`
- Owner: codex

## Scope

- confirm the current `origin/main` still contains the ADR 0359 implementation surfaces
- provision any missing PostgreSQL HA guests required by the governed `postgres-vm` replay
- run the exact-main live apply from this clean worktree and capture receipts
- update ADR, workstream, and release metadata only after the platform replay is verified

## Current Starting Point

- the replay began from `origin/main@bbdb0f7008db4bac81c8cc30a287e728b83790a1` with `VERSION=0.178.129`
- the closeout branch was finally rebased onto `origin/main@063e88c0fe49c278cbfe231a345eaebb145ec404`, where `VERSION=0.178.130`
- the implementation exists in code on this base:
  - `inventory/group_vars/platform_postgres.yml` defines `platform_postgres_clients`
  - `inventory/group_vars/postgres_guests.yml` derives guest source allowlists from the registry
  - the shared `lv3.platform.postgres_client` role is present and per-service postgres roles call it
- the branch-local blockers from the prior exact-main replay are resolved:
  `postgres-apps`, `postgres-data`, and `postgres-replica` now exist in Proxmox and answer through the governed jump path

## Verification To Date

- On 2026-04-13, the focused role regression slice
  `python3 -m pytest -q tests/test_proxmox_guests_role.py tests/test_postgres_vm_role.py tests/test_postgres_vm_access_policy.py`
  passed with `17 passed` after fixing the Proxmox template fallback path, the
  `postgres_vm` default-evaluation regression, and the ADR 0359 registry/HBA exact-main gaps.
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
- On 2026-04-13, the exact-main `postgres-vm` replay converged all four managed
  PostgreSQL guests after fixing the `platform_host` default expansion bug, scoping
  pgaudit grants to databases present on each guest, explicitly loading
  `inventory/group_vars/platform_postgres.yml`, and removing the guest-wide
  `10.10.10.0/24` HBA fallback that bypassed ADR 0359 least-privilege behaviour.
  Evidence is
  `receipts/live-applies/evidence/2026-04-13-ws-0359-live-apply-main-r6-0.178.129.txt`.
- On 2026-04-13, after rebasing onto `origin/main@063e88c0fe49c278cbfe231a345eaebb145ec404`,
  the final exact-tip `postgres-vm` replay from commit
  `080375c1d0f351eba1b9fc4ffc23be2c686288a9` converged cleanly with recap
  `postgres ok=81 changed=3 failed=0` and the three HA guests unchanged; evidence is
  `receipts/live-applies/evidence/2026-04-13-ws-0359-live-apply-main-r7-0.178.131.txt`.
- On 2026-04-13, the live `postgres` guest `pg_hba.conf` contained concrete ADR 0359
  registry entries for `keycloak` and `windmill`; evidence is
  `receipts/live-applies/evidence/2026-04-13-ws-0359-pg-hba-registry-entries-r3-0.178.129.txt`.
- On 2026-04-13, the rebased exact-tip replay reconfirmed `pgaudit`,
  `pgaudit.log=ddl,role`, and `log_connections=on` on all four PostgreSQL guests;
  evidence is
  `receipts/live-applies/evidence/2026-04-13-ws-0359-postgres-runtime-settings-r2-0.178.131.txt`.
- On 2026-04-13, the rebased exact-tip replay reconfirmed the live `postgres`
  guest `pg_hba.conf` registry entries for `keycloak` and `windmill`; evidence is
  `receipts/live-applies/evidence/2026-04-13-ws-0359-pg-hba-registry-entries-r4-0.178.131.txt`.
- On 2026-04-13, representative service logins succeeded from the real client VMs:
  `docker-runtime -> keycloak` and `runtime-control -> windmill`; evidence is
  `receipts/live-applies/evidence/2026-04-13-ws-0359-keycloak-psql-success-r3-0.178.129.txt`
  and `receipts/live-applies/evidence/2026-04-13-ws-0359-windmill-psql-success-r3-0.178.129.txt`.
- On 2026-04-13, the rebased exact-tip replay reconfirmed the representative
  service logins from the real client VMs; evidence is
  `receipts/live-applies/evidence/2026-04-13-ws-0359-keycloak-psql-success-r4-0.178.131.txt`
  and `receipts/live-applies/evidence/2026-04-13-ws-0359-windmill-psql-success-r4-0.178.131.txt`.
- On 2026-04-13, a cross-database login attempt `docker-runtime keycloak -> windmill`
  failed with `no pg_hba.conf entry`, confirming the least-privilege cutover is live;
  evidence is
  `receipts/live-applies/evidence/2026-04-13-ws-0359-keycloak-psql-negative-r3-0.178.129.txt`.
- On 2026-04-13, the rebased exact-tip replay reconfirmed the cross-database denial
  `docker-runtime keycloak -> windmill`; evidence is
  `receipts/live-applies/evidence/2026-04-13-ws-0359-keycloak-psql-negative-r4-0.178.131.txt`.

## Closeout

1. Push the fully validated branch to `origin/main`.
2. Remove the dedicated `ws-0359-main-merge-r2` worktree after the push lands.
