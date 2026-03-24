import importlib.util
from pathlib import Path
import sys
import types


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "plugins" / "filter" / "service_topology.py"


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
