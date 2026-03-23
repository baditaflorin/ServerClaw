# Workstream ADR 0103: Data Classification and Retention Policy

- ADR: [ADR 0103](../adr/0103-data-classification-and-retention-policy.md)
- Title: Four-class data model with per-store retention rules enforced via service configuration, cron jobs, and Ansible, plus a data catalog JSON
- Status: ready
- Branch: `codex/adr-0103-data-retention`
- Worktree: `../proxmox_florin_server-data-retention`
- Owner: codex
- Depends On: `adr-0043-openbao`, `adr-0052-loki`, `adr-0053-tempo`, `adr-0056-keycloak`, `adr-0066-audit-log`, `adr-0077-compose-secrets`, `adr-0087-validation-gate`, `adr-0092-platform-api-gateway`
- Conflicts With: none
- Shared Surfaces: Loki config, Tempo config, Mattermost config, `config/` catalogs, `scripts/maintenance_window_tool.py`

## Scope

- write `config/data-catalog.json` — documents every data store with class, retention, backup scope, access role, PII risk
- update Loki configuration — set `retention_period: 720h` (30 days) in `loki-config.yaml` via Ansible role
- update Tempo configuration — set `max_trace_idle_period: 336h` (14 days) in Tempo config
- update Grafana configuration — set `[annotations] max_age = 2160h` (90 days) in `grafana.ini`
- update Mattermost configuration — enable data retention plugin; set message retention to 2 years
- update NetBox configuration — set `CHANGELOG_RETENTION = 180` (6 months)
- write `scripts/purge_old_receipts.py` — purges `receipts/` subdirectories older than the configured retention period; run by cron weekly
- add cron task to `roles/common/` (or a new `data_retention` role) — weekly purge of old receipts and old audit log entries
- write `scripts/decommission_service.py` — implements the service data cleanup procedure
- add `config/data-catalog.json` to JSON schema validation in the validation gate
- write secret class enforcement check in `scripts/validate_repository_data_models.py` — verify no `*.env` files are committed
- update `roles/preflight/` — add check that no compose `.env` files are present in the repo

## Non-Goals

- Automated PII discovery or classification in logs
- GDPR-compliant data subject erasure (no end-users with GDPR rights in this platform)
- Archive tiers (cold storage for old data)

## Expected Repo Surfaces

- `config/data-catalog.json`
- `scripts/purge_old_receipts.py`
- `scripts/decommission_service.py`
- Loki config files (patched: `retention_period: 720h`)
- Tempo config files (patched: `max_trace_idle_period: 336h`)
- Grafana config (patched: annotations max_age)
- `roles/common/` or `roles/data_retention/` (cron task added)
- `scripts/validate_repository_data_models.py` (patched: `.env` file check)
- `roles/preflight/` (patched: `.env` check)
- `docs/adr/0103-data-classification-and-retention-policy.md`
- `docs/workstreams/adr-0103-data-retention.md`

## Expected Live Surfaces

- Loki retains logs for max 30 days (verify no data older than 30 days in Loki)
- Mattermost data retention plugin is enabled and set to 2 years
- NetBox changelog retention is set to 180 days
- `config/data-catalog.json` documents all data stores

## Verification

- Run `python3 scripts/purge_old_receipts.py --dry-run`; verify it identifies receipts older than retention period
- Check Loki config: `docker exec loki cat /etc/loki/loki-config.yaml | grep retention_period` → `720h`
- Check Tempo config for `max_trace_idle_period: 336h`
- Verify no `*.env` files are tracked in git: `git ls-files | grep '\.env'` → empty
- Run validation gate; verify it rejects a commit with a `.env` file

## Merge Criteria

- `config/data-catalog.json` is valid against its schema and documents all major data stores
- Loki, Tempo, and Grafana retention settings are applied to live services
- `scripts/purge_old_receipts.py` runs without errors against the live `receipts/` directory
- No `*.env` files are tracked in git

## Notes For The Next Assistant

- Loki retention requires the `compactor` component to be enabled in the Loki config; check the existing Loki deployment to see if it is already running as a compactor; if not, add `compactor:` to the Loki config and restart
- Mattermost data retention plugin may require a higher Mattermost plan in some versions (check the installed version); if the plugin is not available, configure retention via the Mattermost database directly with a cron job (`DELETE FROM Posts WHERE CreateAt < NOW() - INTERVAL '2 years'`)
- The `decommission_service.py` script should require explicit confirmation (`--confirm`) before executing any destructive steps; add a dry-run mode that prints what would be deleted
