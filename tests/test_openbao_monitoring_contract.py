import json
from pathlib import Path
from urllib.parse import urlsplit

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _yaml(relative_path: str):
    return yaml.safe_load((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def test_openbao_probe_slo_firewall_and_dashboard_share_one_private_contract():
    host_vars = _yaml("inventory/host_vars/proxmox-host.yml")
    runtime_control = next(guest for guest in host_vars["proxmox_guests"] if guest["name"] == "runtime-control")
    monitoring_rule = next(
        rule
        for rule in host_vars["network_policy"]["guests"]["runtime-control"]["allowed_inbound"]
        if rule.get("source") == "monitoring" and rule.get("protocol") == "tcp"
    )
    assert 8201 in monitoring_rule["ports"]

    health = _yaml("config/health-probe-catalog.json")["services"]["openbao"]
    for phase in ("liveness", "readiness"):
        parsed = urlsplit(health[phase]["url"])
        assert parsed.hostname == runtime_control["ipv4"]
        assert parsed.port == 8201
    assert health["readiness"]["docker_publication"]["bindings"] == [{"host": runtime_control["ipv4"], "port": 8200}]

    slo_catalog = _yaml("config/slo-catalog.json")
    openbao_slo = next(slo for slo in slo_catalog["slos"] if slo["service_id"] == "openbao")
    assert openbao_slo["target_url"] == health["readiness"]["url"]
    assert openbao_slo["probe_module"] == "http_2xx"

    profile = _yaml("config/service-completeness.json")["services"]["openbao"]
    assert profile["requires_secrets"] is True
    assert profile["requires_compose_secrets"] is False
    assert profile["dashboard_file"] == "config/grafana/dashboards/slo-overview.json"
    assert profile["alert_rule_file"] == "config/alertmanager/rules/platform.yml"

    platform_alerts = _yaml("config/alertmanager/rules/platform.yml")
    assert any(rule.get("alert") == "OpenBaoSealed" for group in platform_alerts["groups"] for rule in group["rules"])

    dashboard = json.loads((REPO_ROOT / profile["dashboard_file"]).read_text(encoding="utf-8"))
    assert dashboard["uid"] == "lv3-slo-overview"
    dashboard_exprs = {target["expr"] for panel in dashboard["panels"] for target in panel.get("targets", [])}
    assert "slo:openbao_availability:success_ratio_30d" in dashboard_exprs
    assert "slo:openbao_availability:budget_remaining" in dashboard_exprs
    assert any(panel.get("title") == "openbao-availability" for panel in dashboard["panels"])
