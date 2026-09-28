from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import yaml
from jinja2 import Environment

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import service_completeness


def test_openbao_completeness_is_explicit_and_not_grandfathered() -> None:
    context = service_completeness.load_context()
    profile = context["profiles"]["openbao"]
    result = service_completeness.evaluate_service("openbao", today=dt.date(2026, 9, 28), context=context)

    assert "suppression_preset" not in profile
    assert result.passing, service_completeness.format_service_result(result)
    compose_secrets = next(item for item in result.items if item.item_id == "compose_secrets")
    assert not compose_secrets.required


def test_openbao_observability_assets_match_private_readiness_contract() -> None:
    slo_catalog = json.loads((REPO_ROOT / "config" / "slo-catalog.json").read_text(encoding="utf-8"))
    openbao_slo = next(item for item in slo_catalog["slos"] if item["service_id"] == "openbao")
    assert openbao_slo["id"] == "openbao-availability"
    assert openbao_slo["target_url"].endswith(":8201/v1/sys/health")
    assert "127.0.0.1" not in openbao_slo["target_url"]
    assert "playbook_execution_host_patterns.runtime_control" in openbao_slo["target_url"]

    target_file = REPO_ROOT / "config" / "prometheus" / "file_sd" / "slo_targets.yml"
    rendered_targets = Environment().from_string(target_file.read_text(encoding="utf-8")).render(
        hostvars={"runtime-control": {"ansible_host": "192.0.2.92"}},
        playbook_execution_host_patterns={"runtime_control": {"production": "runtime-control"}},
        playbook_execution_env="production",
    )
    target_groups = yaml.safe_load(rendered_targets)
    openbao_target_group = next(item for item in target_groups if item["labels"].get("service_id") == "openbao")
    assert openbao_target_group["targets"] == ["http://192.0.2.92:8201/v1/sys/health"]

    dashboard = json.loads(
        (REPO_ROOT / "config" / "grafana" / "dashboards" / "openbao.json").read_text(encoding="utf-8")
    )
    expressions = {
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    }
    assert dashboard["uid"] == "lv3-openbao"
    assert 'probe_success{service="openbao",probe_kind="readiness"}' in expressions
    assert "slo:openbao_availability:success_ratio_30d" in expressions

    alert_rules = yaml.safe_load(
        (REPO_ROOT / "config" / "alertmanager" / "rules" / "openbao.yml").read_text(encoding="utf-8")
    )
    alerts = alert_rules["groups"][0]["rules"]
    assert any(rule["alert"] == "OpenBaoUnavailable" for rule in alerts)
