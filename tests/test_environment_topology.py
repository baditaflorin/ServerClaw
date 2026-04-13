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
