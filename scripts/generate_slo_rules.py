#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error
from slo_tracking import (
    GRAFANA_DASHBOARD_PATH,
    GRAFANA_DASHBOARD_TITLE,
    GRAFANA_DASHBOARD_UID,
    PROMETHEUS_ALERTS_PATH,
    PROMETHEUS_DATASOURCE_UID,
    PROMETHEUS_RULES_PATH,
    PROMETHEUS_TARGETS_PATH,
    SLO_CATALOG_PATH,
    default_grafana_url,
    error_budget_ratio,
    load_slo_catalog,
    metric_slug,
    slo_metric_queries,
    slo_success_expr,
)


FAST_BURN_MULTIPLIER = 14
SLOW_BURN_MULTIPLIER = 3
RECORDING_RULES_PER_SLO = 9
ALERT_RULES_PER_SLO = 3


def promql_string(expr: str) -> str:
    return " ".join(expr.split())


def dump_yaml_text(payload: Any) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - direct runtime guard
        from controller_automation_toolkit import PYYAML_INSTALL_HINT

        raise RuntimeError(PYYAML_INSTALL_HINT) from exc

    class IndentedSafeDumper(yaml.SafeDumper):
        def increase_indent(self, flow: bool = False, indentless: bool = False) -> Any:
            return super().increase_indent(flow, False)

    return yaml.dump(
        payload,
        Dumper=IndentedSafeDumper,
        sort_keys=False,
        default_flow_style=False,
    )


def _indent_yaml_block(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join((prefix + line) if line.strip() else line for line in text.rstrip("\n").splitlines())


def build_marked_rule_file(catalog: dict[str, Any], payload: dict[str, Any], *, rules_per_slo: int) -> str:
    group = payload["groups"][0]
    rules = group["rules"]
    parts = [
        "groups:\n",
        f"  - name: {group['name']}\n",
        f"    interval: {group['interval']}\n",
        "    rules:\n",
    ]
    offset = 0
    for slo in catalog["slos"]:
        service_id = slo["service_id"]
        service_rules = rules[offset : offset + rules_per_slo]
        offset += rules_per_slo
        parts.append(f"# BEGIN SERVICE: {service_id}\n")
        parts.append(_indent_yaml_block(dump_yaml_text(service_rules), 6) + "\n")
        parts.append(f"# END SERVICE: {service_id}\n")
    return "".join(parts)


def build_marked_targets_file(catalog: dict[str, Any], targets: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for slo, target in zip(catalog["slos"], targets, strict=True):
        service_id = slo["service_id"]
        parts.append(f"# BEGIN SERVICE: {service_id}\n")
        parts.append(dump_yaml_text([target]))
        parts.append(f"# END SERVICE: {service_id}\n")
    return "".join(parts)


def build_recording_rules(catalog: dict[str, Any]) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    for slo in catalog["slos"]:
        slug = metric_slug(slo["id"])
        window_days = int(slo["window_days"])
        queries = slo_metric_queries(slo)
        success_windows = {
            "5m": queries["success_5m"],
            "1h": queries["success_1h"],
            f"{window_days}d": queries["success_30d"],
        }
        for window, record_name in success_windows.items():
            rules.append(
                {
                    "record": record_name,
                    "expr": promql_string(slo_success_expr(slo, window)),
                    "labels": {
                        "slo_id": slo["id"],
                        "service_id": slo["service_id"],
                        "indicator": slo["indicator"],
                    },
                }
            )

        rules.extend(
            [
                {
                    "record": queries["error_5m"],
                    "expr": f"1 - {queries['success_5m']}",
                    "labels": {
                        "slo_id": slo["id"],
                        "service_id": slo["service_id"],
                        "indicator": slo["indicator"],
                    },
                },
                {
                    "record": queries["error_1h"],
                    "expr": f"1 - {queries['success_1h']}",
                    "labels": {
                        "slo_id": slo["id"],
                        "service_id": slo["service_id"],
                        "indicator": slo["indicator"],
                    },
                },
                {
                    "record": queries["error_30d"],
                    "expr": f"1 - {queries['success_30d']}",
                    "labels": {
                        "slo_id": slo["id"],
                        "service_id": slo["service_id"],
                        "indicator": slo["indicator"],
                    },
                },
                {
                    "record": queries["budget_remaining"],
                    "expr": (f"clamp_min(1 - ({queries['error_30d']} / {error_budget_ratio(slo):.6f}), 0)"),
                    "labels": {
                        "slo_id": slo["id"],
                        "service_id": slo["service_id"],
                        "indicator": slo["indicator"],
                    },
                },
                {
                    "record": queries["burn_rate_1h"],
                    "expr": f"{queries['error_1h']} / {error_budget_ratio(slo):.6f}",
                    "labels": {
                        "slo_id": slo["id"],
                        "service_id": slo["service_id"],
                        "indicator": slo["indicator"],
                    },
                },
                {
                    "record": queries["time_to_budget_exhaustion_days"],
                    "expr": (
                        f"({queries['budget_remaining']} * {window_days}) / clamp_min({queries['burn_rate_1h']}, 0.001)"
                    ),
                    "labels": {
                        "slo_id": slo["id"],
                        "service_id": slo["service_id"],
                        "indicator": slo["indicator"],
                    },
                },
            ]
        )

    return {
        "groups": [
            {
                "name": "slo_recording_rules",
                "interval": "5m",
                "rules": rules,
            }
        ]
    }


def build_alert_rules(catalog: dict[str, Any]) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    for slo in catalog["slos"]:
        queries = slo_metric_queries(slo)
        error_budget = error_budget_ratio(slo)
        base_labels = {
            "severity": "warning",
            "service_id": slo["service_id"],
            "slo_id": slo["id"],
            "indicator": slo["indicator"],
        }
        rules.append(
            {
                "alert": f"SLOFastBurn_{metric_slug(slo['id'])}",
                "expr": (
                    f"({queries['error_5m']} > ({FAST_BURN_MULTIPLIER} * {error_budget:.6f}))"
                    f" and ({queries['error_1h']} > ({FAST_BURN_MULTIPLIER} * {error_budget:.6f}))"
                ),
                "for": "2m",
                "labels": {**base_labels, "severity": "critical"},
                "annotations": {
                    "summary": f"{slo['id']} is burning its error budget at {FAST_BURN_MULTIPLIER}x",
                    "description": slo["description"],
                    "runbook": str(Path("docs/runbooks/slo-tracking.md")),
                },
            }
        )
        rules.append(
            {
                "alert": f"SLOSlowBurn_{metric_slug(slo['id'])}",
                "expr": f"{queries['error_1h']} > ({SLOW_BURN_MULTIPLIER} * {error_budget:.6f})",
                "for": "60m",
                "labels": base_labels,
                "annotations": {
                    "summary": f"{slo['id']} is burning its error budget at {SLOW_BURN_MULTIPLIER}x",
                    "description": slo["description"],
                    "runbook": str(Path("docs/runbooks/slo-tracking.md")),
                },
            }
        )
        rules.append(
            {
                "alert": f"SLOBudgetCritical_{metric_slug(slo['id'])}",
                "expr": f"{queries['budget_remaining']} < 0.10",
                "for": "10m",
                "labels": {**base_labels, "severity": "critical"},
                "annotations": {
                    "summary": f"{slo['id']} has less than 10% error budget remaining",
                    "description": slo["description"],
                    "runbook": str(Path("docs/runbooks/slo-tracking.md")),
                },
            }
        )
    return {
        "groups": [
            {
                "name": "slo_alert_rules",
                "interval": "1m",
                "rules": rules,
            }
        ]
    }


def build_targets(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    targets = []
    for slo in catalog["slos"]:
        targets.append(
            {
                "targets": [slo["target_url"]],
                "labels": {
                    "service_id": slo["service_id"],
                    "slo_id": slo["id"],
                    "indicator": slo["indicator"],
                    "probe_module": slo["probe_module"],
                },
            }
        )
    return targets


def stat_panel(
    panel_id: int, title: str, expr: str, x: int, y: int, *, unit: str, thresholds: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    panel: dict[str, Any] = {
        "id": panel_id,
        "type": "stat",
        "title": title,
        "datasource": {"type": "prometheus", "uid": PROMETHEUS_DATASOURCE_UID},
        "gridPos": {"h": 4, "w": 6, "x": x, "y": y},
        "fieldConfig": {
            "defaults": {
                "unit": unit,
            },
            "overrides": [],
        },
        "options": {
            "colorMode": "value",
            "graphMode": "area",
            "justifyMode": "center",
            "orientation": "auto",
            "reduceOptions": {
                "calcs": ["lastNotNull"],
                "fields": "",
                "values": False,
            },
            "showPercentChange": False,
            "textMode": "auto",
            "wideLayout": True,
        },
        "targets": [
            {
                "refId": "A",
                "expr": expr,
                "legendFormat": title,
            }
        ],
    }
    if thresholds is not None:
        panel["fieldConfig"]["defaults"]["color"] = {"mode": "thresholds"}
        panel["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": thresholds}
    return panel


def text_panel(panel_id: int, title: str, content: str, y: int) -> dict[str, Any]:
    return {
        "id": panel_id,
        "type": "text",
        "title": title,
        "gridPos": {"h": 3, "w": 24, "x": 0, "y": y},
        "options": {
            "content": content,
            "mode": "markdown",
        },
    }


def build_dashboard(catalog: dict[str, Any]) -> dict[str, Any]:
    grafana_url = default_grafana_url().rstrip("/")
    panels: list[dict[str, Any]] = []
    y = 0
    panel_id = 1
    thresholds = [
        {"color": "red", "value": None},
        {"color": "yellow", "value": 0.1},
        {"color": "green", "value": 0.5},
    ]
    for slo in catalog["slos"]:
        queries = slo_metric_queries(slo)
        heading = f"### {slo['id']}\n\n{slo['description']}\n\nService: `{slo['service_id']}`"
        if slo["indicator"] == "latency":
            heading += f"\n\nLatency threshold: `{int(slo['latency_threshold_ms'])}ms`"
        heading += (
            f"\n\n[Open Grafana]({grafana_url}/d/{GRAFANA_DASHBOARD_UID}/{GRAFANA_DASHBOARD_UID}?var-slo={slo['id']})"
        )
        panels.append(text_panel(panel_id, slo["id"], heading, y))
        panel_id += 1
        y += 3
        panels.append(
            stat_panel(
                panel_id,
                "30d Compliance",
                queries["success_30d"],
                0,
                y,
                unit="percentunit",
            )
        )
        panel_id += 1
        panels.append(
            stat_panel(
                panel_id,
                "Budget Remaining",
                queries["budget_remaining"],
                6,
                y,
                unit="percentunit",
                thresholds=thresholds,
            )
        )
        panel_id += 1
        panels.append(
            stat_panel(
                panel_id,
                "Burn Rate (1h)",
                queries["burn_rate_1h"],
                12,
                y,
                unit="none",
            )
        )
        panel_id += 1
        panels.append(
            stat_panel(
                panel_id,
                "Budget Exhaustion (days)",
                queries["time_to_budget_exhaustion_days"],
                18,
                y,
                unit="d",
            )
        )
        panel_id += 1
        y += 4

    return {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 0,
        "links": [],
        "panels": panels,
        "refresh": "1m",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["slo", "reliability", "adr-0096"],
        "templating": {
            "list": [
                {
                    "name": "slo",
                    "label": "SLO",
                    "type": "custom",
                    "query": ",".join(slo["id"] for slo in catalog["slos"]),
                    "current": {"selected": False, "text": "all", "value": "all"},
                    "includeAll": True,
                    "multi": False,
                }
            ]
        },
        "time": {"from": "now-30d", "to": "now"},
        "timezone": "",
        "title": GRAFANA_DASHBOARD_TITLE,
        "uid": GRAFANA_DASHBOARD_UID,
        "version": 1,
        "weekStart": "",
    }


def write_dashboard(path: Path, dashboard: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dashboard, indent=2) + "\n")


def outputs_match(catalog: dict[str, Any]) -> bool:
    expected_rules = build_recording_rules(catalog)
    expected_alerts = build_alert_rules(catalog)
    expected_targets = build_targets(catalog)
    expected_dashboard = build_dashboard(catalog)
    if not PROMETHEUS_RULES_PATH.exists() or not PROMETHEUS_ALERTS_PATH.exists():
        return False
    if not PROMETHEUS_TARGETS_PATH.exists() or not GRAFANA_DASHBOARD_PATH.exists():
        return False

    import yaml

    current_rules = yaml.safe_load(PROMETHEUS_RULES_PATH.read_text())
    current_alerts = yaml.safe_load(PROMETHEUS_ALERTS_PATH.read_text())
    current_targets = yaml.safe_load(PROMETHEUS_TARGETS_PATH.read_text())
    current_dashboard = json.loads(GRAFANA_DASHBOARD_PATH.read_text())
    return (
        current_rules == expected_rules
        and current_alerts == expected_alerts
        and current_targets == expected_targets
        and current_dashboard == expected_dashboard
    )


def generate() -> None:
    catalog = load_slo_catalog(SLO_CATALOG_PATH)
    rules = build_recording_rules(catalog)
    alerts = build_alert_rules(catalog)
    targets = build_targets(catalog)
    PROMETHEUS_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROMETHEUS_RULES_PATH.write_text(
        build_marked_rule_file(catalog, rules, rules_per_slo=RECORDING_RULES_PER_SLO),
        encoding="utf-8",
    )
    PROMETHEUS_ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROMETHEUS_ALERTS_PATH.write_text(
        build_marked_rule_file(catalog, alerts, rules_per_slo=ALERT_RULES_PER_SLO),
        encoding="utf-8",
    )
    PROMETHEUS_TARGETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROMETHEUS_TARGETS_PATH.write_text(build_marked_targets_file(catalog, targets), encoding="utf-8")
    write_dashboard(GRAFANA_DASHBOARD_PATH, build_dashboard(catalog))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Prometheus and Grafana SLO assets from config/slo-catalog.json."
    )
    parser.add_argument("--write", action="store_true", help="Write generated assets to the repository.")
    parser.add_argument("--check", action="store_true", help="Verify that committed generated assets are up to date.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.write and not args.check:
        parser.error("one of --write or --check is required")

    try:
        if args.write:
            generate()
            return 0
        catalog = load_slo_catalog(SLO_CATALOG_PATH)
        if not outputs_match(catalog):
            raise ValueError("generated SLO assets are out of date; run scripts/generate_slo_rules.py --write")
        return 0
    except Exception as exc:
        return emit_cli_error("generate-slo-rules", exc)


if __name__ == "__main__":
    raise SystemExit(main())
