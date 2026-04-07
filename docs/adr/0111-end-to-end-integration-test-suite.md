# ADR 0111: End-to-End Integration Test Suite

- Status: Accepted
- Implementation Status: Partial Implemented
- Implemented In Repo Version: 0.100.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
- Date: 2026-03-23

## Context

The platform has unit-level validation (schema validation in ADR 0037, ansible-lint in ADR 0087) and service-level health probes (ADR 0064). What it does not have is **cross-cutting integration tests** that verify the platform works as a whole system:

- Can a new operator log in to Keycloak and access Grafana via SSO?
- Does secret rotation for a service actually result in the service still being functional afterwards?
- If the API gateway returns a valid JWT, does Windmill accept it?
- Does a deployment triggered from the ops portal actually apply the correct Ansible playbook and update the service?
- If Postgres failover happens (ADR 0098), do all dependent services reconnect within 60 seconds?

None of these questions can be answered by health probes alone. A health probe for Keycloak tells you whether Keycloak's HTTP server is running. It does not tell you whether Keycloak can actually authenticate a user and issue a JWT that other services accept.

The absence of integration tests means the first time the full platform is exercised is in production, by an operator who is either deploying or troubleshooting. This is not acceptable for a platform that is the operator's primary tool.

## Decision

We will build an **end-to-end integration test suite** (`tests/integration/`) written in Python using `pytest` with `httpx` for HTTP interactions, targeting the live platform on the staging network. The test suite runs on every ADR workstream branch before merge and as a scheduled nightly verification job.

### Test scope and organisation

```
tests/integration/
├── conftest.py              # Shared fixtures: auth tokens, service URLs, test users
├── test_authentication.py   # SSO and JWT flows
├── test_platform_api.py     # API gateway endpoints
├── test_secret_management.py # OpenBao and secret rotation
├── test_deployment.py       # Deployment trigger and verification
├── test_observability.py    # Logs, traces, metrics query
├── test_data_services.py    # Postgres connectivity and NetBox queries
├── test_failover.py         # Postgres HA failover (destructive; opt-in only)
└── test_backup_recovery.py  # Backup restore (destructive; weekly schedule only)
```

### Authentication integration tests

```python
# tests/integration/test_authentication.py

@pytest.fixture
def keycloak_token(keycloak_url: str, test_credentials: dict) -> str:
    """Obtain a real Keycloak JWT for the test operator."""
    response = httpx.post(
        f"{keycloak_url}/realms/lv3/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "platform-cli",
            "username": test_credentials["username"],
            "password": test_credentials["password"],
        }
    )
    assert response.status_code == 200, f"Keycloak token request failed: {response.text}"
    return response.json()["access_token"]


def test_keycloak_issues_valid_jwt(keycloak_token: str):
    """Verify Keycloak issues a parseable JWT with correct claims."""
    claims = decode_jwt(keycloak_token)
    assert claims["iss"] == "https://sso.lv3.org/realms/lv3"
    assert "platform-read" in claims.get("realm_access", {}).get("roles", [])


def test_api_gateway_accepts_keycloak_jwt(keycloak_token: str, gateway_url: str):
    """Verify the API gateway validates the Keycloak JWT and returns platform health."""
    response = httpx.get(
        f"{gateway_url}/v1/platform/health",
        headers={"Authorization": f"Bearer {keycloak_token}"}
    )
    assert response.status_code == 200
    health = response.json()
    assert health["status"] in ("healthy", "degraded")


def test_grafana_sso_login(keycloak_token: str, grafana_url: str):
    """Verify that a Keycloak token grants access to the Grafana API."""
    response = httpx.get(
        f"{grafana_url}/api/org",
        headers={"Authorization": f"Bearer {keycloak_token}"}
    )
    assert response.status_code == 200
```

### Platform API integration tests

```python
# tests/integration/test_platform_api.py

def test_service_catalog_returns_all_services(gateway_url: str, keycloak_token: str):
    """Verify the gateway returns all expected services from the capability catalog."""
    response = httpx.get(f"{gateway_url}/v1/platform/services",
                         headers=auth_header(keycloak_token))
    assert response.status_code == 200
    services = {s["id"] for s in response.json()["services"]}
    required = {"keycloak", "grafana", "openbao", "windmill", "netbox", "mattermost"}
    assert required.issubset(services), f"Missing services: {required - services}"


def test_drift_endpoint_returns_report(gateway_url: str, keycloak_token: str):
    """Verify the drift endpoint returns a valid (possibly empty) report."""
    response = httpx.get(f"{gateway_url}/v1/platform/drift",
                         headers=auth_header(keycloak_token))
    assert response.status_code == 200
    report = response.json()
    assert "detected_at" in report
    assert report["overall"] in ("clean", "warn", "critical")


def test_health_endpoint_all_services_probed(gateway_url: str, keycloak_token: str):
    response = httpx.get(f"{gateway_url}/v1/platform/health",
                         headers=auth_header(keycloak_token))
    data = response.json()
    for service in data["services"]:
        assert service["status"] in ("healthy", "degraded", "down"), \
            f"Unexpected status for {service['id']}: {service['status']}"
```

### Secret rotation integration test

```python
# tests/integration/test_secret_management.py

def test_secret_rotation_leaves_service_healthy(gateway_url: str, keycloak_token: str):
    """
    Rotate the NetBox DB password, verify NetBox is still healthy afterwards.
    This is the most important integration test: proves that rotation automation works end-to-end.
    """
    # Trigger rotation for netbox
    response = httpx.post(
        f"{gateway_url}/v1/platform/secrets/rotate",
        json={"service": "netbox"},
        headers=auth_header(keycloak_token)
    )
    assert response.status_code == 202  # accepted, async

    job_id = response.json()["job_id"]

    # Poll for completion (max 120 seconds)
    for _ in range(24):
        time.sleep(5)
        status = httpx.get(f"{gateway_url}/v1/platform/jobs/{job_id}",
                           headers=auth_header(keycloak_token)).json()
        if status["state"] in ("complete", "failed"):
            break

    assert status["state"] == "complete", f"Rotation failed: {status.get('error')}"

    # Verify NetBox is still healthy
    netbox_health = httpx.get(f"{gateway_url}/v1/platform/health/netbox",
                              headers=auth_header(keycloak_token))
    assert netbox_health.json()["status"] == "healthy"
```

### Deployment integration test

```python
# tests/integration/test_deployment.py

def test_deployment_trigger_runs_and_succeeds(gateway_url: str, keycloak_token: str):
    """Trigger a no-op deployment (uptime-kuma; low blast radius) and verify it completes."""
    response = httpx.post(
        f"{gateway_url}/v1/platform/deploy",
        json={"service": "uptime-kuma", "check_mode": True},  # check_mode = dry run
        headers=auth_header(keycloak_token)
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    # Wait for Windmill workflow to complete
    result = poll_job(gateway_url, job_id, keycloak_token, timeout=120)
    assert result["state"] == "complete"
    assert result["changed_count"] == 0, "check_mode deployment should report zero changes on a clean platform"
```

### Postgres failover test (opt-in, destructive)

```python
# tests/integration/test_failover.py

@pytest.mark.destructive
@pytest.mark.skipif(not os.getenv("ENABLE_FAILOVER_TEST"), reason="Destructive failover test requires explicit opt-in")
def test_postgres_failover_services_recover(proxmox_api, gateway_url, keycloak_token):
    """
    Stop Postgres on the primary, verify Patroni promotes the replica,
    verify all dependent services recover within 60 seconds.
    """
    # Stop Postgres on primary
    proxmox_api.exec(vmid=150, command="systemctl stop postgresql")
    time.sleep(35)  # Wait for Patroni TTL (30s) + VIP failover (~5s)

    # All dependent services should have reconnected via the VIP
    services_to_check = ["keycloak", "windmill", "netbox", "mattermost"]
    for service in services_to_check:
        health = httpx.get(f"{gateway_url}/v1/platform/health/{service}",
                           headers=auth_header(keycloak_token))
        assert health.json()["status"] == "healthy", \
            f"{service} did not recover within 60 seconds of Postgres failover"

    # Restart Postgres on the original primary (it becomes a standby)
    proxmox_api.exec(vmid=150, command="systemctl start postgresql")
```

### Test execution

**On every ADR branch (pre-merge):**
```bash
pytest tests/integration/ -m "not destructive" --timeout=300
```

**Nightly (02:30 UTC, after backup restore verification completes):**
```bash
pytest tests/integration/ -m "not destructive" --timeout=300
```

**Monthly (first Sunday, explicitly scheduled, with ENABLE_FAILOVER_TEST=1):**
```bash
pytest tests/integration/ --timeout=600
```

### Test operator identity

The integration tests use a dedicated Keycloak user `test-runner@lv3.org` with `platform-read` role for read-only tests and `platform-operator` role for mutation tests. This account is:
- Created by the operator onboarding workflow (ADR 0108)
- Credentials stored in OpenBao at `platform/test-runner/credentials`
- Automatically rotated weekly by the secret rotation workflow (ADR 0065)
- Never used for manual operator sessions — dedicated to automation only

### Results reporting

Test results are published to:
- The mutation audit log (ADR 0066): every test run is a mutation log entry
- Grafana: test pass/fail rate as a metric (via `pytest-metrics`)
- Mattermost `#platform-ops`: nightly summary (pass count, fail count, duration)
- GlitchTip (ADR 0061): failing tests create issues automatically

## Consequences

**Positive**
- Platform-wide correctness is verified continuously, not assumed; the first sign of a cross-service breakage is a failing integration test, not a production incident
- The secret rotation test proves that the most important operational workflow (secret rotation) actually works end-to-end — not just that the script runs
- The failover test provides confidence in the Postgres HA setup (ADR 0098) before it is needed in an actual emergency
- Failing tests on an ADR branch block merge, preventing cross-service regressions from reaching `main`

**Negative / Trade-offs**
- Integration tests run against the live staging (or production, if staging is not available) platform; they must be carefully designed to be idempotent and low-impact; a bug in a test can cause real service disruption
- The secret rotation test actually rotates a secret and restarts a service; running this on every PR would be too disruptive — it is scoped to nightly runs only
- The `test-runner` Keycloak account must be maintained and its credentials rotated; this adds operational overhead

## Alternatives Considered

- **Molecule for Ansible role testing**: molecule tests individual roles in isolation; does not test cross-service integration; both are needed, not either/or
- **Contract testing (Pact)**: verifies API contracts between producer and consumer services; excellent for microservices teams; over-engineered for a single-operator platform where all services are in the same repo
- **Manual smoke testing after each deployment**: the current state; inconsistent; does not catch regressions over time; not scalable

## Implementation Notes

- Repository implementation landed in `0.100.0` with the environment-aware runner in [scripts/integration_suite.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/integration_suite.py), the opt-in live test matrix under [tests/integration/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/tests/integration), and the nightly wrapper at [config/windmill/scripts/nightly-integration-tests.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/nightly-integration-tests.py).
- The validation contract now includes a non-destructive gate entry in [config/validation-gate.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/validation-gate.json), while [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile) exposes `make integration-tests` and `make nightly-integration-tests` for local and worker execution.
- Operator guidance for targets, environment variables, reports, and destructive toggles is documented in [docs/runbooks/integration-test-suite.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/integration-test-suite.md).
- No live platform version is claimed here. Scheduling the recurring worker job, provisioning `test-runner@lv3.org`, and storing its credentials in OpenBao remain follow-up apply tasks from `main`.

## Related ADRs

- ADR 0044: Windmill (deployment tests trigger Windmill workflows)
- ADR 0056: Keycloak (authentication tests use Keycloak OIDC)
- ADR 0061: GlitchTip (failing tests create issues here)
- ADR 0064: Health probe contracts (integration tests verify probe endpoints)
- ADR 0066: Mutation audit log (test runs are recorded here)
- ADR 0088: Ephemeral infrastructure fixtures (destructive tests use ephemeral VMs)
- ADR 0092: Unified platform API gateway (most tests call the gateway)
- ADR 0098: Postgres HA (failover test validates this ADR)
- ADR 0106: Ephemeral environment lifecycle (test VMs use the ephemeral pool)
- ADR 0108: Operator onboarding (test-runner account provisioned via this workflow)
