from __future__ import annotations

import base64
import json
import os
import socket
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(os.environ.get("LV3_INTEGRATION_REPO_ROOT", Path(__file__).resolve().parents[2]))
REALM = os.environ.get("LV3_INTEGRATION_KEYCLOAK_REALM", "lv3")


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    text: str
    headers: dict[str, str]

    def json(self) -> Any:
        return json.loads(self.text)


@dataclass(frozen=True)
class IntegrationConfig:
    environment: str
    verify_tls: bool
    gateway_url: str | None
    keycloak_url: str | None
    grafana_url: str | None
    netbox_url: str | None
    windmill_url: str | None
    openbao_url: str | None
    postgres_dsn: str | None
    loki_query_url: str | None
    tempo_push_url: str | None
    tempo_query_url: str | None
    grafana_api_token: str | None
    netbox_api_token: str | None
    openbao_token: str | None
    keycloak_username: str | None
    keycloak_password: str | None
    keycloak_client_id: str
    keycloak_client_secret: str | None
    preissued_bearer_token: str | None
    expected_issuer: str | None
    proxmox_api_url: str | None
    proxmox_node: str
    proxmox_token_id: str | None
    proxmox_token_secret: str | None
    required_service_ids: tuple[str, ...]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return value.rstrip("/")


def load_service_catalog() -> dict[str, Any]:
    path = REPO_ROOT / "config" / "service-capability-catalog.json"
    return json.loads(path.read_text(encoding="utf-8"))


def find_service(catalog: dict[str, Any], service_id: str) -> dict[str, Any] | None:
    for service in catalog.get("services", []):
        if service.get("id") == service_id:
            return service
    return None


def resolve_service_url(catalog: dict[str, Any], service_id: str, environment: str) -> str | None:
    service = find_service(catalog, service_id)
    if service is None:
        return None
    env_entry = service.get("environments", {}).get(environment)
    if isinstance(env_entry, dict) and env_entry.get("status") == "active":
        return normalize_url(env_entry.get("url"))
    if environment == "production":
        return normalize_url(service.get("public_url") or service.get("internal_url"))
    return None


def http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = 20,
    verify: bool = True,
) -> HttpResponse:
    try:
        import httpx
    except ModuleNotFoundError:
        encoded_data: bytes | None = None
        request_headers = dict(headers or {})
        if json_body is not None:
            encoded_data = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        elif data is not None:
            encoded_data = urllib.parse.urlencode(data).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        request = urllib.request.Request(
            url,
            data=encoded_data,
            headers=request_headers,
            method=method.upper(),
        )
        context = None
        if not verify and url.startswith("https://"):
            import ssl

            context = ssl._create_unverified_context()  # noqa: SLF001
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            body = response.read().decode("utf-8")
            return HttpResponse(
                status_code=response.status,
                text=body,
                headers=dict(response.headers),
            )
    else:
        response = httpx.request(
            method,
            url,
            headers=headers,
            data=data,
            json=json_body,
            timeout=timeout,
            verify=verify,
        )
        return HttpResponse(
            status_code=response.status_code,
            text=response.text,
            headers=dict(response.headers),
        )


def decode_jwt(token: str) -> dict[str, Any]:
    try:
        import jwt
    except ModuleNotFoundError:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8"))
    return jwt.decode(token, options={"verify_signature": False})


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def poll_job(
    config: IntegrationConfig,
    token: str,
    job_id: str,
    *,
    timeout_seconds: int = 120,
    interval_seconds: int = 5,
) -> dict[str, Any]:
    if not config.gateway_url:
        raise RuntimeError("gateway_url is required to poll a platform job")

    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] = {"state": "running"}
    while time.monotonic() < deadline:
        response = http_request(
            "GET",
            f"{config.gateway_url}/v1/platform/jobs/{job_id}",
            headers=auth_header(token),
            verify=config.verify_tls,
        )
        if response.status_code == 200:
            last_payload = response.json()
            if last_payload.get("state") in {"complete", "completed", "failed"}:
                return last_payload
        time.sleep(interval_seconds)
    return last_payload


def parse_postgres_dsn(dsn: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(dsn)
    host = parsed.hostname
    port = parsed.port or 5432
    if not host:
        raise ValueError(f"Could not resolve a hostname from DSN: {dsn}")
    return host, port


def maybe_import_psycopg2():
    try:
        import psycopg2
    except ModuleNotFoundError:
        pytest.skip("psycopg2 is not installed; install requirements/integration-tests.txt for SQL checks")
    return psycopg2


@pytest.fixture(scope="session")
def integration_config() -> IntegrationConfig:
    catalog = load_service_catalog()
    environment = os.environ.get("LV3_INTEGRATION_ENVIRONMENT", "production")
    keycloak_url = normalize_url(os.environ.get("LV3_INTEGRATION_KEYCLOAK_URL")) or resolve_service_url(
        catalog, "keycloak", environment
    )
    expected_issuer = normalize_url(os.environ.get("LV3_INTEGRATION_EXPECTED_ISSUER"))
    if expected_issuer is None and keycloak_url:
        expected_issuer = f"{keycloak_url}/realms/{REALM}"

    required_ids = os.environ.get(
        "LV3_INTEGRATION_REQUIRED_SERVICE_IDS",
        "keycloak,grafana,openbao,windmill,netbox,mattermost",
    )
    return IntegrationConfig(
        environment=environment,
        verify_tls=env_bool("LV3_INTEGRATION_VERIFY_TLS", default=True),
        gateway_url=normalize_url(os.environ.get("LV3_INTEGRATION_GATEWAY_URL")),
        keycloak_url=keycloak_url,
        grafana_url=normalize_url(os.environ.get("LV3_INTEGRATION_GRAFANA_URL"))
        or resolve_service_url(catalog, "grafana", environment),
        netbox_url=normalize_url(os.environ.get("LV3_INTEGRATION_NETBOX_URL"))
        or resolve_service_url(catalog, "netbox", environment),
        windmill_url=normalize_url(os.environ.get("LV3_INTEGRATION_WINDMILL_URL"))
        or resolve_service_url(catalog, "windmill", environment),
        openbao_url=normalize_url(os.environ.get("LV3_INTEGRATION_OPENBAO_URL"))
        or resolve_service_url(catalog, "openbao", environment),
        postgres_dsn=os.environ.get("LV3_INTEGRATION_POSTGRES_DSN")
        or resolve_service_url(catalog, "postgres", environment),
        loki_query_url=normalize_url(os.environ.get("LV3_INTEGRATION_LOKI_QUERY_URL")),
        tempo_push_url=normalize_url(os.environ.get("LV3_INTEGRATION_TEMPO_PUSH_URL")),
        tempo_query_url=normalize_url(os.environ.get("LV3_INTEGRATION_TEMPO_QUERY_URL")),
        grafana_api_token=os.environ.get("LV3_GRAFANA_TOKEN"),
        netbox_api_token=os.environ.get("LV3_NETBOX_TOKEN"),
        openbao_token=os.environ.get("LV3_OPENBAO_TOKEN"),
        keycloak_username=os.environ.get("LV3_TEST_RUNNER_USERNAME"),
        keycloak_password=os.environ.get("LV3_TEST_RUNNER_PASSWORD"),
        keycloak_client_id=os.environ.get("LV3_KEYCLOAK_PASSWORD_GRANT_CLIENT_ID", "platform-cli"),
        keycloak_client_secret=os.environ.get("LV3_KEYCLOAK_PASSWORD_GRANT_CLIENT_SECRET"),
        preissued_bearer_token=os.environ.get("LV3_TEST_BEARER_TOKEN"),
        expected_issuer=expected_issuer,
        proxmox_api_url=normalize_url(os.environ.get("LV3_PROXMOX_API_URL")),
        proxmox_node=os.environ.get("LV3_PROXMOX_NODE", "proxmox"),
        proxmox_token_id=os.environ.get("LV3_PROXMOX_TOKEN_ID"),
        proxmox_token_secret=os.environ.get("LV3_PROXMOX_TOKEN_SECRET"),
        required_service_ids=tuple(item.strip() for item in required_ids.split(",") if item.strip()),
    )


@pytest.fixture(autouse=True)
def require_network_opt_in() -> None:
    if os.environ.get("LV3_INTEGRATION_ENABLE_NETWORK_TESTS") != "1":
        pytest.skip("Set LV3_INTEGRATION_ENABLE_NETWORK_TESTS=1 or use scripts/integration_suite.py")


@pytest.fixture(scope="session")
def keycloak_token(integration_config: IntegrationConfig) -> str:
    if integration_config.preissued_bearer_token:
        return integration_config.preissued_bearer_token
    if not integration_config.keycloak_url:
        pytest.skip("Keycloak URL is not configured for this environment")
    if not integration_config.keycloak_username or not integration_config.keycloak_password:
        pytest.skip("LV3_TEST_RUNNER_USERNAME/LV3_TEST_RUNNER_PASSWORD are not configured")

    payload = {
        "grant_type": "password",
        "client_id": integration_config.keycloak_client_id,
        "username": integration_config.keycloak_username,
        "password": integration_config.keycloak_password,
    }
    if integration_config.keycloak_client_secret:
        payload["client_secret"] = integration_config.keycloak_client_secret

    response = http_request(
        "POST",
        f"{integration_config.keycloak_url}/realms/{REALM}/protocol/openid-connect/token",
        data=payload,
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def grafana_bearer_token(
    integration_config: IntegrationConfig,
    keycloak_token: str,
) -> str:
    return integration_config.grafana_api_token or keycloak_token


@pytest.fixture(scope="session")
def catalog_services() -> set[str]:
    catalog = load_service_catalog()
    return {service["id"] for service in catalog.get("services", []) if "id" in service}


@pytest.fixture(scope="session")
def proxmox_api_headers(integration_config: IntegrationConfig) -> dict[str, str]:
    if not integration_config.proxmox_token_id or not integration_config.proxmox_token_secret:
        pytest.skip("LV3_PROXMOX_TOKEN_ID and LV3_PROXMOX_TOKEN_SECRET are required")
    return {
        "Authorization": (
            f"PVEAPIToken={integration_config.proxmox_token_id}"
            f"={integration_config.proxmox_token_secret}"
        )
    }


@pytest.fixture(scope="session")
def proxmox_agent_exec(integration_config: IntegrationConfig, proxmox_api_headers: dict[str, str]):
    if not integration_config.proxmox_api_url:
        pytest.skip("LV3_PROXMOX_API_URL is required for destructive Proxmox guest-agent tests")

    def runner(vmid: int, command: str, *args: str) -> dict[str, Any]:
        response = http_request(
            "POST",
            (
                f"{integration_config.proxmox_api_url}/api2/json/nodes/"
                f"{integration_config.proxmox_node}/qemu/{vmid}/agent/exec"
            ),
            headers=proxmox_api_headers,
            data={"command": command, "arg": list(args)},
            verify=integration_config.verify_tls,
        )
        assert response.status_code == 200, response.text
        return response.json()

    return runner


def require_url(url: str | None, message: str) -> str:
    if not url:
        pytest.skip(message)
    return url


def tcp_connects(host: str, port: int, timeout_seconds: float = 5.0) -> None:
    with socket.create_connection((host, port), timeout=timeout_seconds):
        return
