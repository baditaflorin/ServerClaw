import importlib.util
from pathlib import Path
import sys
import types

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "plugins" / "filter" / "service_topology.py"
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
                "public_hostname": "grafana.lv3.org",
                "edge": {
                    "enabled": True,
                    "tls": True,
                    "kind": "proxy",
                    "upstream": "http://10.10.10.40:3000",
                    "noindex": True,
                    "proxy_hide_headers": ["X-Grafana-Version", "Via"],
                    "blocked_exact_paths": [{"path": "/api/health", "status": 404}],
                },
            }
        }
    )
    assert sites == [
        {
            "hostname": "grafana.lv3.org",
            "kind": "proxy",
            "noindex": True,
            "upstream": "http://10.10.10.40:3000",
            "proxy_hide_headers": ["X-Grafana-Version", "Via"],
            "blocked_exact_paths": [{"path": "/api/health", "status": 404}],
        }
    ]


def test_platform_inventory_points_headscale_edge_at_proxmox_internal_bridge() -> None:
    platform_vars = yaml.safe_load(PLATFORM_VARS_PATH.read_text())
    headscale = platform_vars["platform_service_topology"]["headscale"]

    assert headscale["edge"]["upstream"] == "http://10.10.10.1:8080"
    assert headscale["urls"]["internal"] == "http://10.10.10.1:8080"
    assert platform_vars["headscale_internal_url"] == "http://10.10.10.1:8080"


def test_root_headscale_playbook_does_not_duplicate_edge_site_overrides() -> None:
    playbook = yaml.safe_load(HEADSCALE_PLAYBOOK_PATH.read_text())

    edge_publish_play = next(
        play
        for play in playbook
        if play.get("name") == "Publish Headscale on the NGINX edge"
    )

    assert "vars" not in edge_publish_play


def test_edge_certificate_domains_include_aliases() -> None:
    filters = load_module()
    domains = filters.service_topology_edge_certificate_domains(
        {
            "coolify_apps": {
                "public_hostname": "apps.lv3.org",
                "edge": {
                    "enabled": True,
                    "tls": True,
                    "kind": "proxy",
                    "upstream": "http://10.10.10.70:80",
                    "aliases": ["*.apps.lv3.org"],
                },
            }
        }
    )

    assert domains == ["*.apps.lv3.org", "apps.lv3.org"]
