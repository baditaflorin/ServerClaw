import importlib.util
from pathlib import Path
import sys
import types

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "plugins"
    / "filter"
    / "service_topology.py"
)
PLATFORM_VARS_PATH = REPO_ROOT / "inventory" / "group_vars" / "platform.yml"
HEADSCALE_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "headscale.yml"


def load_module():
    ansible_module = types.ModuleType("ansible")
    ansible_errors = types.ModuleType("ansible.errors")

    class AnsibleFilterError(Exception):
        pass

    ansible_errors.AnsibleFilterError = AnsibleFilterError
    ansible_module.errors = ansible_errors
    sys.modules.setdefault("ansible", ansible_module)
    sys.modules["ansible.errors"] = ansible_errors
    spec = importlib.util.spec_from_file_location("service_topology_filters", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_edge_sites_preserve_proxy_hardening_fields() -> None:
    filters = load_module()
    sites = filters.service_topology_edge_sites(
        {
            "grafana": {
                "public_hostname": "grafana.example.com",
                "edge": {
                    "enabled": True,
                    "tls": True,
                    "kind": "proxy",
                    "upstream": "http://10.10.10.40:3000",
                    "noindex": True,
                    "proxy_hide_headers": ["X-Grafana-Version", "Via"],
                    "blocked_exact_paths": [{"path": "/api/health", "status": 404}],
                    "crawl_policy_enabled": False,
                    "preserve_upstream_security_headers": True,
                    "security_headers_enabled": False,
                },
            }
        }
    )
    assert sites == [
        {
            "hostname": "grafana.example.com",
            "kind": "proxy",
            "noindex": True,
            "upstream": "http://10.10.10.40:3000",
            "proxy_hide_headers": ["X-Grafana-Version", "Via"],
            "blocked_exact_paths": [{"path": "/api/health", "status": 404}],
            "crawl_policy_enabled": False,
            "preserve_upstream_security_headers": True,
            "security_headers_enabled": False,
        }
    ]


def test_edge_sites_preserve_exact_redirects() -> None:
    filters = load_module()
    sites = filters.service_topology_edge_sites(
        {
            "nextcloud": {
                "public_hostname": "cloud.example.com",
                "edge": {
                    "enabled": True,
                    "tls": True,
                    "kind": "proxy",
                    "upstream": "http://10.10.10.20:8084",
                    "exact_redirects": [
                        {"path": "/.well-known/carddav", "target": "/remote.php/dav/", "status": 301},
                        {"path": "/.well-known/caldav", "target": "/remote.php/dav/", "status": 301},
                    ],
                },
            }
        }
    )

    assert sites == [
        {
            "hostname": "cloud.example.com",
            "kind": "proxy",
            "upstream": "http://10.10.10.20:8084",
            "exact_redirects": [
                {"path": "/.well-known/carddav", "target": "/remote.php/dav/", "status": 301},
                {"path": "/.well-known/caldav", "target": "/remote.php/dav/", "status": 301},
            ],
        }
    ]


def test_private_edge_sites_require_tls_and_an_explicit_source_allowlist() -> None:
    filters = load_module()
    topology = {
        "gitea": {
            "public_hostname": "git.example.com",
            "private_edge": {
                "enabled": True,
                "tls": True,
                "upstream": "http://10.10.10.92:3003",
                "allow_cidrs": ["10.10.10.1/32"],
            },
        }
    }

    sites = filters.service_topology_private_edge_sites(topology)
    assert sites == [
        {
            "hostname": "git.example.com",
            "kind": "proxy",
            "upstream": "http://10.10.10.92:3003",
            "private_only": True,
            "allow_cidrs": ["10.10.10.1/32"],
        }
    ]


def test_private_edge_site_rejects_an_invalid_allowlist() -> None:
    filters = load_module()
    topology = {
        "gitea": {
            "public_hostname": "git.example.com",
            "private_edge": {
                "enabled": True,
                "tls": True,
                "upstream": "http://10.10.10.92:3003",
                "allow_cidrs": ["not-a-network"],
            },
        }
    }

    try:
        filters.service_topology_private_edge_sites(topology)
    except filters.AnsibleFilterError as exc:
        assert "invalid CIDR" in str(exc)
    else:
        raise AssertionError("invalid private-edge source CIDR must be rejected")


def test_private_edge_site_rejects_public_source_networks() -> None:
    filters = load_module()
    topology = {
        "gitea": {
            "public_hostname": "git.example.com",
            "private_edge": {
                "enabled": True,
                "tls": True,
                "upstream": "http://192.0.2.10:3003",
                "allow_cidrs": ["0.0.0.0/0"],
            },
        }
    }

    try:
        filters.service_topology_private_edge_sites(topology)
    except filters.AnsibleFilterError as exc:
        assert "private unicast network" in str(exc)
    else:
        raise AssertionError("private edge routes must reject public source networks")


def test_edge_sites_preserve_proxy_header_and_security_policy_controls() -> None:
    filters = load_module()
    sites = filters.service_topology_edge_sites(
        {
            "plausible": {
                "public_hostname": "analytics.example.com",
                "edge": {
                    "enabled": True,
                    "tls": True,
                    "kind": "proxy",
                    "upstream": "http://10.10.10.20:8016",
                    "crawl_policy_enabled": False,
                    "preserve_upstream_security_headers": True,
                    "security_headers_enabled": False,
                },
            }
        }
    )

    assert sites == [
        {
            "hostname": "analytics.example.com",
            "kind": "proxy",
            "upstream": "http://10.10.10.20:8016",
            "crawl_policy_enabled": False,
            "preserve_upstream_security_headers": True,
            "security_headers_enabled": False,
        }
    ]


def test_platform_inventory_points_headscale_edge_at_proxmox_internal_bridge() -> None:
    platform_vars = yaml.safe_load(PLATFORM_VARS_PATH.read_text())
    headscale = platform_vars["platform_service_topology"]["headscale"]

    expected_internal_url = headscale["urls"]["internal"]
    assert headscale["edge"]["upstream"] == expected_internal_url
    assert platform_vars["headscale_internal_url"] == expected_internal_url
    assert expected_internal_url.endswith(":8080")


def test_root_headscale_playbook_does_not_duplicate_edge_site_overrides() -> None:
    playbook = yaml.safe_load(HEADSCALE_PLAYBOOK_PATH.read_text())

    edge_publish_play = next(play for play in playbook if play.get("name") == "Publish Headscale on the NGINX edge")

    assert "vars" not in edge_publish_play


def test_edge_certificate_domains_include_aliases() -> None:
    filters = load_module()
    domains = filters.service_topology_edge_certificate_domains(
        {
            "coolify_apps": {
                "public_hostname": "apps.example.com",
                "edge": {
                    "enabled": True,
                    "tls": True,
                    "kind": "proxy",
                    "upstream": "http://10.10.10.70:80",
                    "aliases": ["*.apps.example.com"],
                },
            }
        }
    )

    assert domains == ["*.apps.example.com", "apps.example.com"]


def test_service_topology_dns_records_include_additional_records() -> None:
    filters = load_module()
    records = filters.service_topology_dns_records(
        {
            "minio": {
                "dns": {
                    "managed": True,
                    "visibility": "public",
                    "name": "minio",
                    "type": "A",
                    "target": "203.0.113.1",
                    "ttl": 60,
                    "additional_records": [
                        {
                            "name": "minio-console",
                            "type": "A",
                            "target": "203.0.113.1",
                            "ttl": 60,
                        }
                    ],
                }
            }
        }
    )

    assert records == [
        {"name": "minio", "type": "A", "value": "203.0.113.1", "ttl": 60},
        {"name": "minio-console", "type": "A", "value": "203.0.113.1", "ttl": 60},
    ]
