# Workstream ws-0292-superset-live-apply: Live Apply ADR 0292 Superset From Latest `origin/main`

- ADR: [ADR 0292](../adr/0292-apache-superset-as-the-sql-first-business-intelligence-layer.md)
- Title: Deploy Apache Superset on `docker-runtime`, publish it at `bi.example.com`, register read-only SQL datasources, and verify the SQL-first BI surface end to end
- Status: live_applied
- Included In Repo Version: 0.177.129
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-01-adr-0292-superset-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.82
- Implemented On: 2026-04-01
- Live Applied On: 2026-04-01
- Release Date: 2026-04-01
- Branch: `codex/ws-0292-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0292-live-apply`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0042-postgresql-as-the-shared-relational-database`, `adr-0063-keycloak-sso-for-internal-services`, `adr-0077-compose-secret-injection-pattern`, `adr-0283-plausible-analytics-as-the-privacy-first-web-traffic-analytics-layer`
- Conflicts With: none

## Scope

- deploy Apache Superset on `docker-runtime` as a repo-managed Docker Compose service built from a pinned upstream base image
- store Superset metadata in PostgreSQL on `postgres` using a dedicated `superset` schema inside the shared `postgres` database
- delegate browser sign-in to Keycloak through a repo-managed OIDC client and publish the service at `bi.example.com`
- register read-only PostgreSQL datasources plus Plausible ClickHouse in the Superset metadata plane
- leave branch-local live-apply evidence, tests, and workstream state ready for the final exact-main replay and merge closeout

## Non-Goals

- replacing Grafana for operational alerting or replacing JupyterHub for notebook-driven analysis
- introducing a new time-series compatibility layer solely to translate InfluxDB 2 into a SQL datasource if upstream Superset support is absent
- modifying protected release truth until the final exact-main integration step

## Expected Repo Surfaces

- `docs/adr/0292-apache-superset-as-the-sql-first-business-intelligence-layer.md`
- `docs/runbooks/configure-superset.md`
- `docs/workstreams/ws-0292-superset-live-apply.md`
- `inventory/host_vars/proxmox-host.yml`
- `inventory/group_vars/platform.yml`
- `playbooks/superset.yml`
- `playbooks/services/superset.yml`
- `collections/ansible_collections/lv3/platform/roles/superset_postgres/`
- `collections/ansible_collections/lv3/platform/roles/superset_runtime/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `config/*catalog*.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `Makefile`
- `tests/`
- `receipts/live-applies/`
- `workstreams.yaml`

## Expected Live Surfaces

- the Superset runtime published privately on `docker-runtime`
- the public hostname `bi.example.com` on the shared NGINX edge
- a repo-managed Keycloak OIDC client for Superset
- a repo-managed metadata schema and read-only datasource role on the PostgreSQL primary
- committed evidence covering local health, public publication, datasource registration, and seeded dashboard verification

## Ownership Notes

- this workstream owns the Superset runtime, PostgreSQL bootstrap, Keycloak client, and live-apply receipts for ADR 0292 Superset
- `docker-runtime`, `postgres`, `nginx-edge`, and the shared Keycloak runtime are shared live surfaces, so replay must stay within the governed playbook path and avoid unrelated mutations
- `ws-0292-live-apply` already exists on `origin/main` for the separately merged Lago ADR, so this Superset closeout uses the disambiguated workstream id `ws-0292-superset-live-apply` to preserve both histories safely

## Verification

- the latest realistic integration baseline was refreshed from `origin/main` commit `3ccef3ea09cba8a3b5f4f46af28713aad4b8fb9e`, which still carried repository version `0.177.128` and platform version `0.130.81` before this closeout promoted the shared truth
- focused branch and mainline regression coverage stayed green across the Superset, MinIO recovery, and vulnerability-budget surfaces, including the earlier `104 passed` Superset contract bundle plus fresh `tests/test_minio_runtime_role.py` and `tests/test_vulnerability_budget.py` passes preserved in `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-minio-recovery-tests-r1.txt` and `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-vulnerability-budget-tests-r1.txt`
- the exact-main replay `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=superset env=production` completed cleanly on the integrated release tree, preserved in `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-mainline-live-apply-r3.txt`, with final recap `docker-runtime : ok=316 changed=2 failed=0`, `localhost : ok=24 changed=0 failed=0`, `nginx-edge : ok=46 changed=4 failed=0`, and `postgres : ok=80 changed=0 failed=0`
- fresh guest-local verification on `docker-runtime` confirmed local `/health`, healthy `superset` and `superset-openbao-agent` containers, and a successful `verify-local` report for the managed datasource and dashboard contract; the transcript is preserved in `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-direct-runtime-verification-r2.txt`
- fresh public verification on `https://bi.example.com` confirmed public `/health`, the Keycloak redirect host `sso.example.com`, and the expected managed dashboard plus chart contract through the authenticated API; the transcript is preserved in `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-public-verification-r3.txt`
- shared operational recovery was re-verified after documented Docker-runtime disk pressure had blocked MinIO and Restic on the same guest; the recovery evidence lives in `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-docker-runtime-disk-pressure-r1.txt`, `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-docker-runtime-disk-pressure-r2.txt`, `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-restic-trigger-r4.txt`, and `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-mainline-live-apply-r3.txt`
- the integrated repository automation gates passed from this exact tree: `make validate`, `make remote-validate`, `make pre-push-gate`, and `make check-build-server`, preserved in `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-mainline-validate-r4.txt`, `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-mainline-remote-validate-r1.txt`, `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-mainline-pre-push-gate-r1.txt`, and `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-mainline-check-build-server-r1.txt`

## Results

- ADR 0292 is now implemented and first verified from canonical `main` truth as repository version `0.177.129` and platform version `0.130.82`
- the branch-local proof remains preserved in `receipts/live-applies/2026-04-01-adr-0292-superset-live-apply.json`, while the canonical mainline truth is recorded in `receipts/live-applies/2026-04-01-adr-0292-superset-mainline-live-apply.json`
- the final closeout also hardens the shared MinIO runtime recovery contract for stale containerd task state and restores Python 3.9 compatibility for the Superset vulnerability-budget preflight used by the governed live-apply wrapper

## Notes

- `docs/runbooks/docker-runtime-disk-pressure.md` now records the safe cache and journal cleanup path that restored MinIO and Restic on `docker-runtime` without hiding the shared-host dependency
- the final exact-main replay uses the governed `live-apply-service` wrapper rather than an ad hoc compose restart so the recorded receipt matches the repo automation path expected for future replays
- controller-side `make restic-config-backup env=production` was exercised as part of the final validation bundle and still timed out on `restic snapshots --json` even after widening the probe budget to 180 seconds; the exact-main live-apply proof remains green, the new receipt-sync helper is covered by tests, and the timeout transcript is preserved in `receipts/live-applies/evidence/2026-04-01-ws-0292-superset-mainline-restic-config-backup-r2.txt` for ADR 0302 follow-up work
