# Workstream ADR 0111: End-to-End Integration Test Suite

- ADR: [ADR 0111](../adr/0111-end-to-end-integration-test-suite.md)
- Title: pytest-based cross-service integration tests covering SSO flows, API gateway, secret rotation, deployments, and Postgres failover; run on every ADR branch and nightly
- Status: merged
- Branch: `codex/adr-0111-integration-tests`
- Worktree: `.worktrees/adr-0111`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0056-keycloak`, `adr-0061-glitchtip`, `adr-0064-health-probes`, `adr-0066-audit-log`, `adr-0088-ephemeral-fixtures`, `adr-0092-platform-api-gateway`, `adr-0098-postgres-ha`, `adr-0106-ephemeral-lifecycle`, `adr-0108-operator-onboarding`
- Conflicts With: none
- Shared Surfaces: `tests/`, `scripts/integration_suite.py`, `requirements/integration-tests.txt`, `Makefile`, `config/validation-gate.json`, `config/workflow-catalog.json`, Windmill scheduled workflows, Keycloak realm, `docs/runbooks/`

## Scope Delivered

- write `tests/integration/conftest.py` — shared fixtures: Keycloak token acquisition, gateway URL resolution, test operator identity
- write `tests/integration/test_authentication.py` — Keycloak JWT issuance, API gateway JWT validation, Grafana SSO access
- write `tests/integration/test_platform_api.py` — service catalog, drift, health, dependency graph endpoints
- write `tests/integration/test_secret_management.py` — secret rotation for NetBox (low blast radius); verify service health after rotation
- write `tests/integration/test_deployment.py` — check-mode deployment trigger via API gateway; Windmill workflow completion
- write `tests/integration/test_observability.py` — Loki query returns results, Tempo trace ingestion, Grafana datasource health
- write `tests/integration/test_data_services.py` — Postgres VIP connectivity, NetBox API query, NetBox returns expected VM data
- write `tests/integration/test_failover.py` — Postgres failover smoke test (destructive, opt-in, `@pytest.mark.destructive`)
- write `tests/integration/test_backup_recovery.py` — restore-verification smoke test (destructive, opt-in, weekly only)
- write `requirements/integration-tests.txt` — pinned optional dependencies for richer live runs
- write `scripts/integration_suite.py` — environment-aware ADR 0111 runner with structured JSON reports and gate/nightly mode selection
- write Windmill workflow `nightly-integration-tests` — repo-managed wrapper that runs nightly checks and posts optional Mattermost/GlitchTip notifications
- provision `test-runner@example.com` Keycloak user with `platform-operator` role — via operator onboarding workflow (ADR 0108)
- store test-runner credentials in OpenBao at `platform/test-runner/credentials`
- update `config/validation-gate.json` — add non-destructive integration test run as a pre-merge gate check (runs on build server against staging environment if available, or skips if no staging environment is up)
- add test results to GlitchTip (manual webhook event in the nightly wrapper when configured)
- add `docs/runbooks/integration-test-suite.md` — operator runbook for targets, environment variables, outputs, and destructive toggles

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
- `tests/integration/test_backup_recovery.py`
- `requirements/integration-tests.txt`
- `scripts/integration_suite.py`
- `config/workflow-catalog.json` (patched: nightly workflow registered)
- `config/windmill/scripts/nightly-integration-tests.py`
- `Makefile` (patched: integration test entrypoints added)
- `config/validation-gate.json` (patched: integration test gate added)
- `docs/runbooks/integration-test-suite.md`
- `docs/adr/0111-end-to-end-integration-test-suite.md`
- `docs/workstreams/adr-0111-integration-test-suite.md`

## Expected Live Surfaces

- Windmill `nightly-integration-tests` workflow is scheduled and has at least one successful run
- Mattermost `#platform-ops` received the nightly test summary
- GlitchTip has no open issues from the integration test suite (all tests passing)
- `test-runner@example.com` Keycloak user exists with correct roles

## Verification

- Run `python3 scripts/integration_suite.py --mode gate --environment staging` → structured skip or pass depending on active staging endpoints
- Run `uv run --with pytest python -m pytest tests/test_integration_suite.py tests/test_nightly_integration_tests.py -q` → local ADR 0111 unit coverage passes
- Run `uv run --with pytest python -m pytest tests/integration -m 'integration and not mutation and not destructive' -q` without opt-in env → all tests skip safely instead of probing live endpoints implicitly
- When the build server has live credentials and network access, confirm `test_keycloak_issues_valid_jwt` obtains a real JWT from `sso.example.com`
- When nightly worker secrets are configured, trigger the wrapper and confirm Mattermost/GlitchTip notifications are emitted

## Merge Criteria Result

- Repo-managed runner, gate contract, workflow entry, and operator runbook are implemented
- Local ADR 0111 unit tests pass
- Gate mode records a structured skip instead of a false failure when staging targets are not currently active
- Live rollout of nightly schedule, Keycloak `test-runner@example.com`, and OpenBao credential storage remains a post-merge apply task from `main`

## Notes For The Next Assistant

- The `keycloak_token` fixture uses the resource owner password grant (username/password) which requires the `platform-cli` Keycloak client to have "Direct Access Grants" enabled; verify this is enabled for the `platform-cli` client in the `lv3` realm
- `test_secret_management.py` is a mutation test (it actually rotates a secret); the repo-managed runner enables it only in `nightly` or `destructive` mode and keeps it out of `gate`
- The integration test workflow on the build server must have network access to all platform service URLs (internal DNS must resolve from `docker-build`); verify `sso.example.com` is reachable from the build server via Tailscale or via the internal network
- The nightly wrapper falls back to the existing `mattermost_platform_findings_webhook_url` and `glitchtip_platform_findings_event_url` controller-local secrets if dedicated integration-test webhook overrides are not set yet
