from __future__ import annotations

import json
from pathlib import Path

from platform.runtime_assurance import declared_live_attestation as module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_repo(tmp_path: Path) -> Path:
    write_json(
        tmp_path / "config" / "service-capability-catalog.json",
        {
            "services": [
                {
                    "id": "api_gateway",
                    "name": "Platform API Gateway",
                    "description": "gateway",
                    "category": "automation",
                    "lifecycle_status": "active",
                    "vm": "docker-runtime-lv3",
                    "vmid": 120,
                    "internal_url": "http://10.10.10.20:8083",
                    "public_url": "https://api.lv3.org",
                    "subdomain": "api.lv3.org",
                    "exposure": "edge-published",
                    "health_probe_id": "api_gateway",
                    "environments": {
                        "production": {
                            "status": "active",
                            "url": "https://api.lv3.org",
                            "subdomain": "api.lv3.org",
                        }
                    },
                },
                {
                    "id": "postgres",
                    "name": "Postgres",
                    "description": "database",
                    "category": "data",
                    "lifecycle_status": "active",
                    "vm": "postgres-lv3",
                    "vmid": 150,
                    "internal_url": "postgres://10.10.10.50:5432",
                    "exposure": "private-only",
                    "health_probe_id": "postgres",
                    "environments": {
                        "production": {
                            "status": "active",
                            "url": "postgres://10.10.10.50:5432",
                        }
                    },
                },
            ]
        },
    )
    write_json(
        tmp_path / "config" / "health-probe-catalog.json",
        {
            "services": {
                "api_gateway": {
                    "readiness": {
                        "kind": "http",
                        "url": "http://127.0.0.1:8083/v1/health",
                        "method": "GET",
                        "expected_status": [401],
                        "timeout_seconds": 2,
                    }
                },
                "postgres": {
                    "liveness": {
                        "kind": "tcp",
                        "host": "127.0.0.1",
                        "port": 5432,
                        "timeout_seconds": 2,
                    }
                },
            }
        },
    )
    write_yaml(
        tmp_path / "inventory" / "group_vars" / "platform.yml",
        """
platform_service_topology:
  api_gateway:
    service_name: api-gateway
    owning_vm: docker-runtime-lv3
    private_ip: 10.10.10.20
    public_hostname: api.lv3.org
    urls:
      public: https://api.lv3.org
      internal: http://10.10.10.20:8083
  postgres:
    service_name: postgres
    owning_vm: postgres-lv3
    private_ip: 10.10.10.50
    urls:
      internal: postgres://10.10.10.50:5432
""".lstrip(),
    )
    write_yaml(
        tmp_path / "versions" / "stack.yaml",
        """
repo_version: 0.177.53
platform_version: 0.130.42
observed_state:
  proxmox:
    installed: true
  guests:
    instances:
      - vmid: 120
        name: docker-runtime-lv3
        running: true
      - vmid: 150
        name: postgres-lv3
        running: true
""".lstrip(),
    )
    write_json(
        tmp_path / "receipts" / "live-applies" / "2026-03-28-api-gateway-live-apply.json",
        {
            "receipt_id": "2026-03-28-api-gateway-live-apply",
            "summary": "Replayed api_gateway on docker-runtime-lv3.",
            "workflow_id": "adr-0092-platform-api-gateway-live-apply",
            "recorded_on": "2026-03-28",
            "applied_on": "2026-03-28",
            "targets": [{"kind": "guest", "name": "docker-runtime-lv3"}],
        },
    )
    write_json(
        tmp_path / "receipts" / "live-applies" / "2026-03-28-postgres-live-apply.json",
        {
            "receipt_id": "2026-03-28-postgres-live-apply",
            "summary": "Replayed postgres-lv3 runtime verification.",
            "workflow_id": "adr-0026-postgres-vm-live-apply",
            "recorded_on": "2026-03-28",
            "applied_on": "2026-03-28",
            "targets": [{"kind": "guest", "name": "postgres-lv3"}],
        },
    )
    return tmp_path


def test_collect_declared_live_attestations_rewrites_loopback_contracts(monkeypatch, tmp_path: Path) -> None:
    repo_root = build_repo(tmp_path)
    probed_urls: list[str] = []
    probed_tcp: list[tuple[str, int]] = []
    observed_http_timeouts: list[float] = []
    observed_tcp_timeouts: list[float] = []

    def fake_http_probe(url: str, **kwargs) -> dict[str, object]:
        probed_urls.append(url)
        observed_http_timeouts.append(float(kwargs["timeout_seconds"]))
        if "10.10.10.20:8083" in url:
            return {
                "status": "pass",
                "observed": "HTTP 401",
                "http_status": 401,
                "observed_target": url,
            }
        return {
            "status": "pass",
            "observed": "HTTP 302",
            "http_status": 302,
            "observed_target": url,
        }

    def fake_tcp_probe(host: str, port: int, **kwargs) -> dict[str, object]:
        probed_tcp.append((host, port))
        observed_tcp_timeouts.append(float(kwargs["timeout_seconds"]))
        return {
            "status": "pass",
            "observed": f"TCP {host}:{port}",
            "http_status": None,
            "observed_target": f"{host}:{port}",
        }

    monkeypatch.setattr(module, "http_probe", fake_http_probe)
    monkeypatch.setattr(module, "tcp_probe", fake_tcp_probe)

    payload = module.collect_declared_live_attestations(repo_root=repo_root, timeout_seconds=1.0, max_workers=2)

    assert payload["summary"]["total"] == 2
    assert payload["summary"]["attested"] == 2
    api_gateway = next(item for item in payload["services"] if item["service_id"] == "api_gateway")
    postgres = next(item for item in payload["services"] if item["service_id"] == "postgres")

    assert api_gateway["status"] == "attested"
    assert api_gateway["endpoint_proof"]["declared_target"] == "http://127.0.0.1:8083/v1/health"
    assert api_gateway["endpoint_proof"]["observed_target"] == "http://10.10.10.20:8083/v1/health"
    assert api_gateway["route_proof"]["status"] == "pass"
    assert postgres["route_proof"]["status"] == "not_required"
    assert ("10.10.10.50", 5432) in probed_tcp
    assert "http://10.10.10.20:8083/v1/health" in probed_urls
    assert observed_http_timeouts == [1.0, 1.0]
    assert observed_tcp_timeouts == [1.0]


def test_collect_declared_live_attestations_fails_without_matching_receipt(monkeypatch, tmp_path: Path) -> None:
    repo_root = build_repo(tmp_path)
    (repo_root / "receipts" / "live-applies" / "2026-03-28-api-gateway-live-apply.json").unlink()

    monkeypatch.setattr(
        module,
        "http_probe",
        lambda url, **kwargs: {
            "status": "pass",
            "observed": "HTTP 200",
            "http_status": 200,
            "observed_target": url,
        },
    )
    monkeypatch.setattr(
        module,
        "tcp_probe",
        lambda host, port, **kwargs: {
            "status": "pass",
            "observed": f"TCP {host}:{port}",
            "http_status": None,
            "observed_target": f"{host}:{port}",
        },
    )

    payload = module.collect_declared_live_attestations(repo_root=repo_root, timeout_seconds=1.0, max_workers=2)
    api_gateway = next(item for item in payload["services"] if item["service_id"] == "api_gateway")

    assert api_gateway["status"] == "missing"
    assert api_gateway["receipt_witness"]["status"] == "fail"


def test_collect_declared_live_service_attestation_only_probes_requested_service(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = build_repo(tmp_path)
    seen_services: list[str] = []

    def fake_collect_one_service_attestation(
        repo_root: Path,
        service: dict[str, object],
        environment: str,
        binding: dict[str, object],
        topology: dict[str, object],
        contract: dict[str, object],
        snapshot_by_name: dict[str, object],
        snapshot_by_vmid: dict[int, object],
        stack: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        seen_services.append(str(service["id"]))
        return {
            "service_id": service["id"],
            "service_name": service["name"],
            "environment": environment,
            "status": "attested",
            "declared": {"binding_url": binding.get("url")},
            "host_witness": {"status": "pass"},
            "runtime_identity": {"status": "pass"},
            "endpoint_proof": {"status": "pass"},
            "route_proof": {"status": "not_required"},
            "receipt_witness": {"status": "pass"},
        }

    monkeypatch.setattr(module, "collect_one_service_attestation", fake_collect_one_service_attestation)

    payload = module.collect_declared_live_service_attestation("postgres", repo_root=repo_root, timeout_seconds=1.0)

    assert payload["service_id"] == "postgres"
    assert seen_services == ["postgres"]
