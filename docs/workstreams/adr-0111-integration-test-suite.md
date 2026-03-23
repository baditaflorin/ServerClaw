# Workstream ADR 0111: End-to-End Integration Test Suite

- ADR: [ADR 0111](../adr/0111-end-to-end-integration-test-suite.md)
- Title: pytest-based cross-service integration tests covering SSO flows, API gateway, secret rotation, deployments, and Postgres failover; run on every ADR branch and nightly
- Status: ready
- Branch: `codex/adr-0111-integration-tests`
- Worktree: `../proxmox_florin_server-integration-tests`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0056-keycloak`, `adr-0061-glitchtip`, `adr-0064-health-probes`, `adr-0066-audit-log`, `adr-0088-ephemeral-fixtures`, `adr-0092-platform-api-gateway`, `adr-0098-postgres-ha`, `adr-0106-ephemeral-lifecycle`, `adr-0108-operator-onboarding`
- Conflicts With: none
- Shared Surfaces: `tests/`, `config/validation-gate.json`, Windmill scheduled workflows, Keycloak realm

## Scope

- write `tests/integration/conftest.py` — shared fixtures: Keycloak token acquisition, gateway URL resolution, test operator identity
- write `tests/integration/test_authentication.py` — Keycloak JWT issuance, API gateway JWT validation, Grafana SSO access
- write `tests/integration/test_platform_api.py` — service catalog, drift, health, dependency graph endpoints
- write `tests/integration/test_secret_management.py` — secret rotation for NetBox (low blast radius); verify service health after rotation
- write `tests/integration/test_deployment.py` — check-mode deployment trigger via API gateway; Windmill workflow completion
- write `tests/integration/test_observability.py` — Loki query returns results, Tempo trace ingestion, Grafana datasource health
- write `tests/integration/test_data_services.py` — Postgres VIP connectivity, NetBox API query, NetBox returns expected VM data
- write `tests/integration/test_failover.py` — Postgres failover smoke test (destructive, opt-in, `@pytest.mark.destructive`)
- write `requirements/integration-tests.txt` — pytest, httpx, psycopg2, pytest-asyncio, pytest-metrics
- write Windmill workflow `nightly-integration-tests` — scheduled 02:30 UTC; runs non-destructive tests; posts results to Mattermost
- provision `test-runner@lv3.org` Keycloak user with `platform-operator` role — via operator onboarding workflow (ADR 0108)
- store test-runner credentials in OpenBao at `platform/test-runner/credentials`
- update `config/validation-gate.json` — add non-destructive integration test run as a pre-merge gate check (runs on build server against staging environment if available, or skips if no staging environment is up)
- add test results to GlitchTip (configure `pytest-glitchtip` plugin or manual issue creation on failure)

## Non-Goals

- Unit tests for individual Ansible roles (molecule tests are a separate concern)
- Performance/load testing
- UI testing (ops portal is tested via HTTP API probes, not browser automation)
- Monthly destructive failover test automation (that is scheduled separately by hand to avoid accidents)

## Expected Repo Surfaces

- `tests/integration/conftest.py`
- `tests/integration/test_authentication.py`
- `tests/integration/test_platform_api.py`
- `tests/integration/test_secret_management.py`
- `tests/integration/test_deployment.py`
- `tests/integration/test_observability.py`
- `tests/integration/test_data_services.py`
- `tests/integration/test_failover.py`
- `requirements/integration-tests.txt`
- `config/validation-gate.json` (patched: integration test gate added)
- `docs/adr/0111-end-to-end-integration-test-suite.md`
- `docs/workstreams/adr-0111-integration-tests.md`

## Expected Live Surfaces

- Windmill `nightly-integration-tests` workflow is scheduled and has at least one successful run
- Mattermost `#platform-ops` received the nightly test summary
- GlitchTip has no open issues from the integration test suite (all tests passing)
- `test-runner@lv3.org` Keycloak user exists with correct roles

## Verification

- Run `pytest tests/integration/ -m "not destructive" -v` from the build server → all tests pass
- Confirm `test_keycloak_issues_valid_jwt` obtains a real JWT from `sso.lv3.org`
- Confirm `test_api_gateway_accepts_keycloak_jwt` succeeds against the live gateway
- Confirm `test_secret_rotation_leaves_service_healthy` rotates NetBox's DB password and NetBox health probe passes after rotation
- Nightly workflow triggered manually; results post to Mattermost

## Merge Criteria

- All non-destructive tests pass against the live platform
- `test_secret_management.py::test_secret_rotation_leaves_service_healthy` passes (full end-to-end rotation test)
- Nightly workflow scheduled and has one successful run
- `test-runner@lv3.org` provisioned in Keycloak

## Notes For The Next Assistant

- The `keycloak_token` fixture uses the resource owner password grant (username/password) which requires the `platform-cli` Keycloak client to have "Direct Access Grants" enabled; verify this is enabled for the `platform-cli` client in the `lv3` realm
- `test_secret_management.py` is a mutation test (it actually rotates a secret); run it only once during verification and not as part of any gated pipeline without careful thought about the impact of simultaneous concurrent rotations
- The integration test workflow on the build server must have network access to all platform service URLs (internal DNS must resolve from `docker-build-lv3`); verify `sso.lv3.org` is reachable from the build server via Tailscale or via the internal network
- `poll_job()` helper in `test_deployment.py` must handle Windmill's async job API: `GET /api/v1/job/completed/<job_id>` returns 404 while the job is running, then 200 when complete; implement with retries and exponential backoff up to the timeout
