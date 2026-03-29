# Integration Test Suite

## Purpose

ADR 0111 adds a repo-managed end-to-end integration suite under `tests/integration/`.

The suite is designed to:

- run a non-destructive gate against staging when staging endpoints exist
- run nightly production-oriented smoke and mutation checks through a Windmill wrapper
- keep destructive failover and restore tests opt-in only

## Entrypoints

Manual run with the pinned integration requirements:

```bash
make integration-tests
```

Gate-mode run, matching `config/validation-gate.json`:

```bash
python3 scripts/integration_suite.py --mode gate --environment staging
```

Nightly Windmill-compatible run:

```bash
python3 config/windmill/scripts/nightly-integration-tests.py --repo-path /srv/proxmox_florin_server
```

Windmill seeds the same wrapper at `f/lv3/nightly_integration_tests` for browser-first or API-triggered execution inside the `lv3` workspace.

## Environment Model

The runner resolves defaults from [config/service-capability-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/service-capability-catalog.json) for these services when the selected environment is `active`:

- `keycloak`
- `grafana`
- `netbox`
- `openbao`
- `postgres`
- `windmill`

The platform API gateway is still provided explicitly because ADR 0092 is not yet integrated into the service catalog contract:

- `LV3_INTEGRATION_GATEWAY_URL`

If the chosen environment has no active endpoints in the service catalog and no `LV3_INTEGRATION_*` overrides are provided, the runner writes a structured `skipped` report instead of failing.

## Supported Variables

Core target resolution:

- `LV3_INTEGRATION_ENVIRONMENT`
- `LV3_INTEGRATION_GATEWAY_URL`
- `LV3_INTEGRATION_KEYCLOAK_URL`
- `LV3_INTEGRATION_GRAFANA_URL`
- `LV3_INTEGRATION_NETBOX_URL`
- `LV3_INTEGRATION_OPENBAO_URL`
- `LV3_INTEGRATION_POSTGRES_DSN`
- `LV3_INTEGRATION_WINDMILL_URL`
- `LV3_INTEGRATION_LOKI_QUERY_URL`
- `LV3_INTEGRATION_TEMPO_PUSH_URL`
- `LV3_INTEGRATION_TEMPO_QUERY_URL`
- `LV3_INTEGRATION_VERIFY_TLS`

Authentication and API access:

- `LV3_TEST_RUNNER_USERNAME`
- `LV3_TEST_RUNNER_PASSWORD`
- `LV3_TEST_BEARER_TOKEN`
- `LV3_KEYCLOAK_PASSWORD_GRANT_CLIENT_ID`
- `LV3_KEYCLOAK_PASSWORD_GRANT_CLIENT_SECRET`
- `LV3_GRAFANA_TOKEN`
- `LV3_NETBOX_TOKEN`
- `LV3_OPENBAO_TOKEN`

Destructive and mutation toggles:

- `LV3_RUN_SECRET_ROTATION_TEST`
- `LV3_ENABLE_FAILOVER_TEST`
- `LV3_ENABLE_BACKUP_RECOVERY_TEST`
- `LV3_PROXMOX_API_URL`
- `LV3_PROXMOX_NODE`
- `LV3_PROXMOX_TOKEN_ID`
- `LV3_PROXMOX_TOKEN_SECRET`
- `LV3_POSTGRES_PRIMARY_VMID`

Nightly notification overrides:

- `LV3_MATTERMOST_INTEGRATION_TEST_WEBHOOK_URL`
- `LV3_GLITCHTIP_INTEGRATION_EVENT_URL`

## Outputs

The runner writes JSON reports under:

- `.local/integration-tests/<environment>-<mode>.json`
- `.local/integration-tests/nightly-last-run.json`

Each report includes:

- the execution mode and environment
- discovered targets
- passed, failed, and skipped counts
- per-test outcomes and durations

## Safety Rules

- `gate` mode excludes all `mutation` and `destructive` tests
- `nightly` mode excludes `destructive` tests, but enables the NetBox secret-rotation mutation test by default
- `destructive` mode requires explicit environment toggles and Proxmox API credentials
- the backup-restore and failover tests must never run unintentionally from a generic `pytest` invocation

## Verification

Fast local verification:

```bash
python3 scripts/integration_suite.py --mode gate --environment staging
```

Mutation test opt-in:

```bash
LV3_RUN_SECRET_ROTATION_TEST=1 python3 scripts/integration_suite.py --mode nightly --environment production
```

Destructive failover opt-in:

```bash
LV3_ENABLE_FAILOVER_TEST=1 python3 scripts/integration_suite.py --mode destructive --environment production
```
