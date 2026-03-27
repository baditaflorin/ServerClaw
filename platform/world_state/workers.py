from __future__ import annotations

import asyncio
import http.client
import json
import os
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

from platform.events import build_envelope
from platform.timeouts import TimeoutContext, default_timeout, resolve_timeout_seconds

from ._db import ConnectionFactory, isoformat, parse_timestamp, utc_now
from .materializer import SURFACE_DEFINITIONS, EventPublisher, materialize_surface


Collector = Callable[[Path], Any]
REPO_ROOT_FALLBACK = Path("/srv/proxmox_florin_server")
FIXTURE_ENV_VARS = {
    "proxmox_vms": "WORLD_STATE_PROXMOX_VMS_FIXTURE",
    "service_health": "WORLD_STATE_SERVICE_HEALTH_FIXTURE",
    "container_inventory": "WORLD_STATE_CONTAINER_INVENTORY_FIXTURE",
    "netbox_topology": "WORLD_STATE_NETBOX_TOPOLOGY_FIXTURE",
    "dns_records": "WORLD_STATE_DNS_RECORDS_FIXTURE",
    "tls_cert_expiry": "WORLD_STATE_TLS_CERT_EXPIRY_FIXTURE",
    "opentofu_drift": "WORLD_STATE_OPENTOFU_DRIFT_FIXTURE",
    "openbao_secret_expiry": "WORLD_STATE_OPENBAO_SECRET_EXPIRY_FIXTURE",
    "maintenance_windows": "WORLD_STATE_MAINTENANCE_WINDOWS_FIXTURE",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def fixture_payload(surface: str) -> Any | None:
    fixture_path = os.environ.get(FIXTURE_ENV_VARS[surface], "").strip()
    if not fixture_path:
        return None
    return load_json(Path(fixture_path).expanduser())


def http_get_json(url: str, *, headers: dict[str, str] | None = None, timeout: int | float | None = None) -> Any:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(
        request,
        timeout=resolve_timeout_seconds("http_request", timeout),
    ) as response:
        return json.loads(response.read().decode())


def read_repo_json(repo_root: Path, relative_path: str, default: Any) -> Any:
    path = repo_root / relative_path
    if not path.exists():
        return default
    return load_json(path)


def read_repo_yaml(repo_root: Path, relative_path: str) -> Any:
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime-only dependency
        raise RuntimeError("PyYAML is required to read repository YAML world-state inputs") from exc

    return yaml.safe_load((repo_root / relative_path).read_text())


def command_output(
    command: list[str],
    *,
    cwd: Path,
    timeout: int | float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=resolve_timeout_seconds("subprocess", timeout),
        check=False,
    )


def normalize_proxmox_vm(record: dict[str, Any]) -> dict[str, Any]:
    cpu = record.get("cpu")
    mem = record.get("mem")
    if cpu is None:
        cpu = 0
    if mem is None:
        mem = 0
    return {
        "vmid": int(record.get("vmid", 0)),
        "name": record.get("name") or f"vm-{record.get('vmid', 'unknown')}",
        "node": record.get("node"),
        "status": record.get("status") or "unknown",
        "type": record.get("type") or "qemu",
        "cpu": cpu,
        "maxcpu": record.get("maxcpu", 0),
        "mem": mem,
        "maxmem": record.get("maxmem", 0),
        "disk": record.get("disk", 0),
        "maxdisk": record.get("maxdisk", 0),
        "tags": record.get("tags"),
        "uptime": record.get("uptime", 0),
    }


def collect_proxmox_vms(repo_root: Path) -> list[dict[str, Any]]:
    fixture = fixture_payload("proxmox_vms")
    if fixture is not None:
        return fixture

    if shutil_which("pvesh") is not None:
        result = command_output(
            ["pvesh", "get", "/cluster/resources", "--type", "vm", "--output-format", "json"],
            cwd=repo_root,
            timeout=resolve_timeout_seconds("script_execution"),
        )
        if result.returncode == 0 and result.stdout.strip():
            return [normalize_proxmox_vm(item) for item in json.loads(result.stdout)]

    stack = read_repo_yaml(repo_root, "versions/stack.yaml")
    guests = stack.get("observed_state", {}).get("guests", {}).get("instances", [])
    return [
        {
            "vmid": int(guest["vmid"]),
            "name": guest["name"],
            "node": "proxmox_florin",
            "status": "running" if guest.get("running") else "stopped",
            "type": "qemu",
            "cpu": 0,
            "maxcpu": 0,
            "mem": 0,
            "maxmem": 0,
            "disk": 0,
            "maxdisk": 0,
            "tags": [],
            "uptime": 0,
            "source": "versions/stack.yaml",
        }
        for guest in guests
    ]


def url_for_service(service: dict[str, Any]) -> str | None:
    environments = service.get("environments", {})
    production = environments.get("production", {})
    return production.get("url") or service.get("internal_url") or service.get("public_url")


def health_probe_catalog(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = read_repo_json(repo_root, "config/health-probe-catalog.json", {"services": {}})
    services = payload.get("services", {})
    return services if isinstance(services, dict) else {}


def probe_service(url: str) -> tuple[str, int | None, str | None]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return "unknown", None, None
    request = urllib.request.Request(url, headers={"User-Agent": "lv3-world-state/1.0"})
    try:
        with urllib.request.urlopen(
            request,
            timeout=resolve_timeout_seconds("health_probe"),
        ) as response:
            status_code = getattr(response, "status", None)
            status = "ok" if status_code and status_code < 400 else "degraded"
            return status, status_code, None
    except urllib.error.HTTPError as exc:
        return "degraded", exc.code, str(exc)
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, ssl.SSLError) as exc:
        return "down", None, str(exc)


def probe_http_contract(probe: dict[str, Any]) -> tuple[str, int | None, str | None]:
    url = str(probe.get("url", ""))
    method = str(probe.get("method", "GET")).upper()
    timeout = int(probe.get("timeout_seconds", default_timeout("health_probe")))
    headers = probe.get("headers") if isinstance(probe.get("headers"), dict) else {}
    expected = probe.get("expected_status") if isinstance(probe.get("expected_status"), list) else [200]
    request = urllib.request.Request(url, headers=headers, method=method)
    context = None
    if url.startswith("https://") and probe.get("validate_tls") is False:
        context = ssl._create_unverified_context()  # noqa: SLF001
    try:
        with urllib.request.urlopen(
            request,
            timeout=resolve_timeout_seconds("health_probe", timeout),
            context=context,
        ) as response:
            status_code = getattr(response, "status", None)
        status = "ok" if status_code in expected else "degraded"
        detail = f"HTTP {status_code}" if status_code is not None else "HTTP response"
        return status, status_code, detail
    except urllib.error.HTTPError as exc:
        status = "ok" if exc.code in expected else "degraded"
        return status, exc.code, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, ssl.SSLError) as exc:
        return "down", None, str(exc)


def probe_tcp_contract(probe: dict[str, Any]) -> tuple[str, int | None, str | None]:
    host = str(probe.get("host", ""))
    port = int(probe.get("port", 0))
    timeout = int(probe.get("timeout_seconds", default_timeout("liveness_probe")))
    try:
        with socket.create_connection(
            (host, port),
            timeout=resolve_timeout_seconds("liveness_probe", timeout),
        ):
            return "ok", None, f"TCP {host}:{port}"
    except OSError as exc:
        return "down", None, str(exc)


def probe_via_contract(service: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    for source in ("readiness", "liveness"):
        probe = contract.get(source)
        if not isinstance(probe, dict):
            continue
        kind = probe.get("kind")
        if kind == "http":
            status, http_status, detail = probe_http_contract(probe)
            return {
                "status": status,
                "http_status": http_status,
                "error": None if status == "ok" else detail,
                "detail": detail,
                "probe_source": source,
                "probe_kind": kind,
            }
        if kind == "tcp":
            status, http_status, detail = probe_tcp_contract(probe)
            return {
                "status": status,
                "http_status": http_status,
                "error": None if status == "ok" else detail,
                "detail": detail,
                "probe_source": source,
                "probe_kind": kind,
            }
    url = url_for_service(service)
    status, http_status, detail = probe_service(url) if url else ("unknown", None, "missing URL")
    return {
        "status": status,
        "http_status": http_status,
        "error": None if status == "ok" else detail,
        "detail": detail,
        "probe_source": "service_catalog",
        "probe_kind": "url",
    }


def preferred_probe_source(contract: dict[str, Any]) -> tuple[str, str]:
    for source in ("readiness", "liveness"):
        probe = contract.get(source)
        if not isinstance(probe, dict):
            continue
        kind = str(probe.get("kind") or "").strip() or "unknown"
        return source, kind
    return "service_catalog", "url"


def collect_service_health(repo_root: Path) -> dict[str, Any]:
    fixture = fixture_payload("service_health")
    if fixture is not None:
        return fixture

    catalog = read_repo_json(repo_root, "config/service-capability-catalog.json", {"services": []})
    probe_catalog = health_probe_catalog(repo_root)
    services: list[dict[str, Any]] = []
    for service in catalog.get("services", []):
        if service.get("lifecycle_status") != "active":
            continue
        url = url_for_service(service)
        health_probe_id = str(service.get("health_probe_id") or service.get("id") or "")
        contract = probe_catalog.get(health_probe_id, {})
        try:
            if contract:
                result = probe_via_contract(service, contract)
            else:
                status, http_status, detail = probe_service(url) if url else ("unknown", None, "missing URL")
                result = {
                    "status": status,
                    "http_status": http_status,
                    "error": None if status == "ok" else detail,
                    "detail": detail,
                    "probe_source": "service_catalog",
                    "probe_kind": "url",
                }
        except Exception as exc:  # pragma: no cover - defensive per-service guard
            probe_source, probe_kind = preferred_probe_source(contract)
            result = {
                "status": "down",
                "http_status": None,
                "error": str(exc),
                "detail": str(exc),
                "probe_source": probe_source,
                "probe_kind": probe_kind,
            }
        services.append(
            {
                "service_id": service["id"],
                "vm": service.get("vm"),
                "vmid": service.get("vmid"),
                "url": url,
                "status": result["status"],
                "http_status": result["http_status"],
                "error": result["error"],
                "detail": result["detail"],
                "probe_source": result["probe_source"],
                "probe_kind": result["probe_kind"],
                "uptime_monitor_name": service.get("uptime_monitor_name"),
            }
        )
    status_counts: dict[str, int] = {}
    for service in services:
        status_counts[service["status"]] = status_counts.get(service["status"], 0) + 1
    return {"services": services, "summary": {"total": len(services), "statuses": status_counts}}


def collect_container_inventory(repo_root: Path) -> list[dict[str, Any]]:
    fixture = fixture_payload("container_inventory")
    if fixture is not None:
        return fixture

    if shutil_which("docker") is None:
        return []

    result = command_output(
        ["docker", "ps", "--all", "--format", "{{json .}}"],
        cwd=repo_root,
        timeout=resolve_timeout_seconds("script_execution"),
    )
    if result.returncode != 0:
        return []
    containers = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        containers.append(
            {
                "id": record.get("ID"),
                "image": record.get("Image"),
                "name": record.get("Names"),
                "state": record.get("State"),
                "status": record.get("Status"),
            }
        )
    return containers


def paginated_netbox_list(base_url: str, token: str, path: str) -> list[dict[str, Any]]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}
    results: list[dict[str, Any]] = []
    timeout_ctx = TimeoutContext.for_layer("api_call_chain")
    while url:
        payload = http_get_json(
            url,
            headers=headers,
            timeout=timeout_ctx.timeout_for("http_request", reserve_seconds=1.0),
        )
        if isinstance(payload, dict) and "results" in payload:
            results.extend(payload["results"])
            url = payload.get("next")
            continue
        if isinstance(payload, list):
            results.extend(payload)
            break
        raise RuntimeError(f"Unexpected NetBox payload for {path}: {payload!r}")
    return results


def collect_netbox_topology(repo_root: Path) -> dict[str, Any]:
    fixture = fixture_payload("netbox_topology")
    if fixture is not None:
        return fixture

    netbox_url = os.environ.get("WORLD_STATE_NETBOX_URL", "").strip()
    netbox_token = os.environ.get("WORLD_STATE_NETBOX_TOKEN", "").strip()
    if netbox_url and netbox_token:
        return {
            "source": "netbox_api",
            "devices": paginated_netbox_list(netbox_url, netbox_token, "/api/dcim/devices/"),
            "virtual_machines": paginated_netbox_list(netbox_url, netbox_token, "/api/virtualization/virtual-machines/"),
            "ip_addresses": paginated_netbox_list(netbox_url, netbox_token, "/api/ipam/ip-addresses/"),
            "vlans": paginated_netbox_list(netbox_url, netbox_token, "/api/ipam/vlans/"),
        }

    inventory = read_repo_yaml(repo_root, "inventory/hosts.yml")
    guests = inventory.get("all", {}).get("children", {}).get("lv3_guests", {}).get("hosts", {})
    return {
        "source": "inventory_hosts",
        "devices": [
            {
                "name": "proxmox_florin",
                "role": "proxmox-host",
                "management_ip": inventory["all"]["children"]["proxmox_hosts"]["hosts"]["proxmox_florin"]["ansible_host"],
            }
        ],
        "virtual_machines": [
            {"name": name, "ansible_host": data.get("ansible_host"), "environment": data.get("environment", "production")}
            for name, data in guests.items()
        ],
        "ip_addresses": [
            {"name": name, "address": data.get("ansible_host")} for name, data in guests.items() if data.get("ansible_host")
        ],
        "vlans": [{"name": "guest-network", "vid": 10, "prefix": "10.10.10.0/24"}],
    }


def collect_dns_records(repo_root: Path) -> list[dict[str, Any]]:
    fixture = fixture_payload("dns_records")
    if fixture is not None:
        return fixture

    catalog = read_repo_json(repo_root, "config/subdomain-catalog.json", {"subdomains": []})
    return [
        {
            "fqdn": entry["fqdn"],
            "service_id": entry.get("service_id"),
            "environment": entry.get("environment"),
            "status": entry.get("status"),
            "target": entry.get("target"),
            "target_port": entry.get("target_port"),
            "exposure": entry.get("exposure"),
        }
        for entry in catalog.get("subdomains", [])
    ]


def certificate_expiry(hostname: str, port: int = 443) -> dict[str, Any]:
    context = ssl.create_default_context()
    with socket.create_connection(
        (hostname, port),
        timeout=resolve_timeout_seconds("health_probe"),
    ) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as secure_sock:
            certificate = secure_sock.getpeercert()
    return {
        "not_after": certificate.get("notAfter"),
        "issuer": certificate.get("issuer"),
        "subject": certificate.get("subject"),
    }


def collect_tls_cert_expiry(repo_root: Path) -> dict[str, Any]:
    fixture = fixture_payload("tls_cert_expiry")
    if fixture is not None:
        return fixture

    records = collect_dns_records(repo_root)
    certificates: list[dict[str, Any]] = []
    for record in records:
        hostname = record["fqdn"]
        if record.get("target_port") != 443:
            continue
        try:
            details = certificate_expiry(hostname)
            certificates.append({"fqdn": hostname, "status": "ok", **details})
        except OSError as exc:
            certificates.append({"fqdn": hostname, "status": "error", "error": str(exc)})
    return {"certificates": certificates, "summary": {"total": len(certificates)}}


def summarize_drift(stdout: str, stderr: str, returncode: int) -> dict[str, Any]:
    drift_detected = "No changes." not in stdout
    return {
        "status": "ok" if returncode == 0 else "error",
        "drift_detected": drift_detected,
        "returncode": returncode,
        "stdout_excerpt": "\n".join(stdout.splitlines()[-20:]),
        "stderr_excerpt": "\n".join(stderr.splitlines()[-20:]),
    }


def collect_opentofu_drift(repo_root: Path) -> dict[str, Any]:
    fixture = fixture_payload("opentofu_drift")
    if fixture is not None:
        return fixture

    result = command_output(
        ["make", "tofu-drift", "ENV=production"],
        cwd=repo_root,
        timeout=resolve_timeout_seconds("script_execution", 180),
    )
    return summarize_drift(result.stdout, result.stderr, result.returncode)


def collect_openbao_secret_expiry(repo_root: Path) -> dict[str, Any]:
    fixture = fixture_payload("openbao_secret_expiry")
    if fixture is not None:
        return fixture

    secret_catalog = read_repo_json(repo_root, "config/secret-catalog.json", {"secrets": []})
    now = utc_now()
    leases = []
    for secret in secret_catalog.get("secrets", []):
        last_rotated_at = parse_timestamp(f"{secret['last_rotated_at']}T00:00:00Z")
        rotation_period_days = int(secret.get("rotation_period_days", 0))
        expires_at = last_rotated_at
        if rotation_period_days > 0:
            expires_at = last_rotated_at + timedelta(days=rotation_period_days)
        leases.append(
            {
                "secret_id": secret["id"],
                "owner_service": secret.get("owner_service"),
                "rotation_mode": secret.get("rotation_mode"),
                "last_rotated_at": isoformat(last_rotated_at),
                "expires_at": isoformat(expires_at),
                "expired": expires_at <= now,
            }
        )
    expired = sum(1 for lease in leases if lease["expired"])
    return {"leases": leases, "summary": {"total": len(leases), "expired": expired}}


def collect_maintenance_windows(repo_root: Path) -> dict[str, Any]:
    fixture = fixture_payload("maintenance_windows")
    if fixture is not None:
        return fixture

    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import maintenance_window_tool

    windows = maintenance_window_tool.list_active_windows()
    active_windows = []
    for key, value in windows.items():
        active_windows.append({"key": key, **value})
    return {"active_windows": active_windows, "summary": {"total": len(active_windows)}}


COLLECTORS: dict[str, Collector] = {
    "proxmox_vms": collect_proxmox_vms,
    "service_health": collect_service_health,
    "container_inventory": collect_container_inventory,
    "netbox_topology": collect_netbox_topology,
    "dns_records": collect_dns_records,
    "tls_cert_expiry": collect_tls_cert_expiry,
    "opentofu_drift": collect_opentofu_drift,
    "openbao_secret_expiry": collect_openbao_secret_expiry,
    "maintenance_windows": collect_maintenance_windows,
}


def publish_refresh_event_best_effort(subject: str, payload: dict[str, Any]) -> dict[str, Any]:
    nats_url = os.environ.get("LV3_NATS_URL", "nats://127.0.0.1:4222").strip()
    username = os.environ.get("LV3_NATS_USERNAME", "").strip()
    password = os.environ.get("LV3_NATS_PASSWORD", "").strip()

    try:
        import nats
    except ModuleNotFoundError:
        return {"published": False, "reason": "nats-py not installed"}

    async def _publish() -> None:
        connect_kwargs: dict[str, Any] = {}
        if username and password:
            connect_kwargs.update({"user": username, "password": password})
        client = await nats.connect(nats_url, **connect_kwargs)
        try:
            envelope = build_envelope(subject, payload, actor_id="service/world-state-worker", ts=payload.get("collected_at"))
            await client.publish(subject, json.dumps(envelope).encode())
            await client.flush()
        finally:
            await client.drain()

    try:
        asyncio.run(_publish())
    except Exception as exc:  # pragma: no cover - network failure path
        return {"published": False, "reason": str(exc)}
    return {"published": True, "url": nats_url}


def run_worker(
    surface: str,
    *,
    repo_path: str | Path | None = None,
    dsn: str | None = None,
    publish_nats: bool = True,
    connection_factory: ConnectionFactory | None = None,
    event_publisher: EventPublisher | None = None,
) -> dict[str, Any]:
    if surface not in SURFACE_DEFINITIONS:
        raise ValueError(f"Unknown world-state surface '{surface}'")
    repo_root = Path(repo_path or REPO_ROOT_FALLBACK)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "surface": surface,
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    payload = COLLECTORS[surface](repo_root)
    publish_result = {"published": False, "reason": "disabled"}
    publisher = event_publisher
    if publisher is None and publish_nats:
        published_events: list[dict[str, Any]] = []

        def publisher(subject: str, event: dict[str, Any]) -> None:
            published_events.append(publish_refresh_event_best_effort(subject, event))

        local_publish_results = published_events
    else:
        local_publish_results = []

    event = materialize_surface(
        surface,
        payload,
        connection_factory=connection_factory,
        dsn=dsn,
        event_publisher=publisher,
    )
    if local_publish_results:
        publish_result = local_publish_results[0]
    elif publish_nats and event_publisher is not None:
        publish_result = {"published": True, "reason": "custom publisher"}

    return {
        "status": "ok",
        "surface": surface,
        "summary": SURFACE_DEFINITIONS[surface].summary,
        "record_count": event["record_count"],
        "event": event,
        "publish_result": publish_result,
    }


def shutil_which(command: str) -> str | None:
    try:
        from shutil import which
    except ImportError:  # pragma: no cover - stdlib always available
        return None
    return which(command)
