from __future__ import annotations

import pytest

import environment_topology


def build_environment_catalog() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "environments": [
            {
                "id": "production",
                "name": "Production",
                "status": "active",
                "purpose": "Primary platform environment",
                "base_domain": "example.com",
                "hostname_pattern": "*.example.com",
                "edge_service_id": "nginx_edge",
                "edge_vm": "nginx-edge",
                "ingress_ipv4": "203.0.113.1",
                "topology_model": "single-node-shared-edge",
                "isolation_model": "shared",
            }
        ],
    }


def build_host_vars() -> dict[str, object]:
    return {"proxmox_guests": [{"name": "nginx-edge"}]}


def build_subdomain_catalog(service_id: str) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "reserved_prefixes": [{"prefix": "chat", "owner_adr": "0254", "allowed_fqdns": ["chat.example.com"]}],
        "subdomains": [
            {
                "fqdn": "chat.example.com",
                "service_id": service_id,
                "environment": "production",
                "status": "active",
                "exposure": "edge-published",
                "auth_requirement": "upstream_auth",
                "target": "203.0.113.1",
                "target_port": 443,
                "owner_adr": "0254",
                "tls": {
                    "provider": "letsencrypt",
                    "cert_path": "/etc/letsencrypt/live/lv3-edge/",
                    "auto_renew": True,
                },
            }
        ],
    }


def build_service_catalog(*service_ids: str) -> dict[str, object]:
    services = [
        {
            "id": "nginx_edge",
            "vm": "nginx-edge",
            "environments": {"production": {"status": "active", "url": "https://edge.example.com"}},
        }
    ]
    for service_id in service_ids:
        services.append(
            {
                "id": service_id,
                "vm": "coolify",
                "environments": {
                    "production": {
                        "status": "active",
                        "url": "https://chat.example.com",
                        "subdomain": "chat.example.com",
                    }
                },
            }
        )
    return {"services": services}


def test_validate_environment_references_allows_declared_shared_subdomain() -> None:
    environment_topology.validate_environment_references(
        build_environment_catalog(),
        build_service_catalog("librechat", "serverclaw"),
        build_subdomain_catalog("serverclaw"),
        build_host_vars(),
    )


def test_validate_environment_references_rejects_unrelated_subdomain_owner() -> None:
    with pytest.raises(ValueError, match="subdomain 'chat.example.com' must reference service_id 'librechat'"):
        environment_topology.validate_environment_references(
            build_environment_catalog(),
            build_service_catalog("librechat"),
            build_subdomain_catalog("serverclaw"),
            build_host_vars(),
        )


def test_main_validate_resolves_placeholder_domains_for_private_overlay(monkeypatch: pytest.MonkeyPatch) -> None:
    environment_catalog = build_environment_catalog()
    environment_catalog["environments"][0]["base_domain"] = "example.com"
    environment_catalog["environments"][0]["hostname_pattern"] = "*.example.com"

    service_catalog = {
        "services": [
            {
                "id": "nginx_edge",
                "vm": "nginx-edge",
                "environments": {"production": {"status": "active", "url": "https://edge.example.com"}},
            },
            {
                "id": "api_gateway",
                "vm": "coolify",
                "environments": {
                    "production": {
                        "status": "active",
                        "url": "https://api.example.com",
                        "subdomain": "api.example.com",
                    }
                },
            },
        ]
    }
    subdomain_catalog = {
        "subdomains": [
            {
                "fqdn": "api.example.com",
                "service_id": "api_gateway",
                "environment": "production",
                "status": "active",
            }
        ]
    }

    monkeypatch.setattr(environment_topology, "load_environment_topology", lambda: environment_catalog)
    monkeypatch.setattr(environment_topology, "load_yaml", lambda _path: build_host_vars())
    # ADR 0430 — production code now reads host_vars via load_topology_host_vars
    # (overlay-aware). Patch the overlay-aware loader too so the test sees the
    # fake host_vars instead of the real file on disk.
    monkeypatch.setattr(environment_topology, "load_topology_host_vars", lambda: build_host_vars())

    def fake_load_json(path):
        if path == environment_topology.SERVICE_CATALOG_PATH:
            return service_catalog
        if path == environment_topology.SUBDOMAIN_CATALOG_PATH:
            return subdomain_catalog
        raise AssertionError(path)

    monkeypatch.setattr(environment_topology, "load_json", fake_load_json)
    monkeypatch.setattr(environment_topology, "resolve_public_domain_placeholders", _replace_example_domain)

    assert environment_topology.main(["--validate"]) == 0


def _replace_example_domain(value):
    if isinstance(value, str):
        return value.replace("example.com", "example.com")
    if isinstance(value, list):
        return [_replace_example_domain(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace_example_domain(item) for key, item in value.items()}
    return value
