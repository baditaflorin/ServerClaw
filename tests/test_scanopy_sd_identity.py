"""Identity-matching tests for the Scanopy service-discovery generator.

node_exporter targets are only published when node_uname_info reports a nodename that belongs to the inventory host.
The inventory often carries an FQDN (scrapetheworld.org) while the machine reports its short hostname (scrapetheworld).
These tests pin the first-label rule, its ambiguity guard and the explicit alias option. Nothing here touches a network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT
    / "collections/ansible_collections/lv3/platform/roles/monitoring_vm/files/scanopy-sd/scanopy_sd.py"
)


@pytest.fixture(scope="module")
def sd() -> ModuleType:
    spec = importlib.util.spec_from_file_location("scanopy_sd_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def host(hid: str, *names: str, ip: str = "10.10.10.10") -> dict:
    return {"id": hid, "name": names[0], "names": set(names), "ips": [ip], "ports": [], "fleet": "0docker"}


def resolve(sd: ModuleType, rec: dict, nodename: str | None, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sd, "tcp_state", lambda ip, port: "open" if port == 9100 else "refused")
    monkeypatch.setattr(sd, "nodename_of", lambda ip, port: nodename)
    return sd.resolve_node(rec, {}, {})


def test_first_dns_label_of_an_fqdn_inventory_name_is_accepted(sd, monkeypatch) -> None:
    hosts = sd.assign_node_names([host("a", "scrapetheworld.org", ip="10.10.10.109"), host("b", "docker-prod")])
    result, reachable, mismatch = resolve(sd, hosts[0], "scrapetheworld", monkeypatch)
    assert result == {"addr": "10.10.10.109:9100", "via": "lan", "identity": "verified"}
    assert mismatch is None and reachable


def test_label_match_is_case_insensitive(sd, monkeypatch) -> None:
    hosts = sd.assign_node_names([host("a", "ScrapeTheWorld.ORG", ip="10.10.10.109")])
    result, _, _ = resolve(sd, hosts[0], "SCRAPETHEWORLD", monkeypatch)
    assert result is not None and result["identity"] == "verified"


def test_exact_inventory_name_still_verifies(sd, monkeypatch) -> None:
    hosts = sd.assign_node_names([host("a", "docker-prod")])
    result, _, _ = resolve(sd, hosts[0], "docker-prod", monkeypatch)
    assert result is not None and result["identity"] == "verified"


def test_ambiguous_first_label_is_not_accepted(sd, monkeypatch) -> None:
    hosts = sd.assign_node_names(
        [host("a", "web.example.org", ip="10.10.10.11"), host("b", "web.example.net", ip="10.10.10.12")]
    )
    assert "web" not in hosts[0]["node_names"] and "web" not in hosts[1]["node_names"]
    result, reachable, mismatch = resolve(sd, hosts[0], "web", monkeypatch)
    assert result is None and reachable and mismatch == "web"


def test_label_shared_with_a_bare_name_host_is_ambiguous(sd) -> None:
    hosts = sd.assign_node_names([host("a", "db.example.org"), host("b", "db")])
    assert "db" not in hosts[0]["node_names"]
    assert hosts[1]["node_names"] == {"db"}


def test_real_mismatch_is_still_rejected(sd, monkeypatch) -> None:
    hosts = sd.assign_node_names([host("a", "scrapetheworld.org", ip="10.10.10.109")])
    result, reachable, mismatch = resolve(sd, hosts[0], "docker-build", monkeypatch)
    assert result is None and reachable and mismatch == "docker-build"


def test_ip_literal_names_never_produce_a_label(sd) -> None:
    assert sd.first_label("10.10.10.109") is None
    assert sd.first_label("docker-prod") is None
    assert sd.first_label("scrapetheworld.org") == "scrapetheworld"
    hosts = sd.assign_node_names([host("a", "10.10.10.109")])
    assert hosts[0]["node_names"] == {"10.10.10.109"}


def test_explicit_alias_map_applies_only_to_the_keyed_host(sd, tmp_path, monkeypatch) -> None:
    alias_file = tmp_path / "node-aliases.json"
    alias_file.write_text(json.dumps({"Billing.Example.org": ["legacy-box"], "other": "x"}))
    aliases = sd.load_aliases(str(alias_file))
    hosts = sd.assign_node_names([host("a", "billing.example.org"), host("b", "docker-prod")], aliases)
    result, _, _ = resolve(sd, hosts[0], "legacy-box", monkeypatch)
    assert result is not None and result["identity"] == "verified"
    result, _, mismatch = resolve(sd, hosts[1], "legacy-box", monkeypatch)
    assert result is None and mismatch == "legacy-box"


def test_missing_or_invalid_alias_file_means_no_aliases(sd, tmp_path) -> None:
    assert sd.load_aliases(str(tmp_path / "absent.json")) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2")
    assert sd.load_aliases(str(bad)) == {}
    bad.write_text("[]")
    assert sd.load_aliases(str(bad)) == {}


def test_build_hosts_populates_node_names(sd, monkeypatch) -> None:
    monkeypatch.setitem(sd.CONF, "alias_file", "/nonexistent/aliases.json")
    inv = {
        "daemons": [],
        "services": [],
        "hosts": [
            {
                "id": "h1",
                "name": "scrapetheworld.org",
                "hostname": "scrapetheworld.org",
                "ip_addresses": [{"ip_address": "10.10.10.109"}],
                "ports": [],
                "last_seen_at": None,
            }
        ],
    }
    hosts, _, _ = sd.build_hosts(inv)
    assert len(hosts) == 1 and {"scrapetheworld.org", "scrapetheworld"} <= hosts[0]["node_names"]
