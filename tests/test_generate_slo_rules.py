from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_slo_rules
import slo_tracking


def test_generated_payloads_include_fast_and_slow_burn_alerts():
    catalog = generate_slo_rules.load_slo_catalog(generate_slo_rules.SLO_CATALOG_PATH)
    recording_payload = generate_slo_rules.build_recording_rules(catalog)
    alert_payload = generate_slo_rules.build_alert_rules(catalog)

    assert recording_payload["groups"][0]["name"] == "slo_recording_rules"
    alert_names = {rule["alert"] for rule in alert_payload["groups"][0]["rules"]}
    assert "SLOFastBurn_authentik_availability" in alert_names
    assert "SLOSlowBurn_authentik_availability" in alert_names


def test_generated_slo_files_include_decommission_block_markers():
    for path in (
        generate_slo_rules.PROMETHEUS_RULES_PATH,
        generate_slo_rules.PROMETHEUS_ALERTS_PATH,
        generate_slo_rules.PROMETHEUS_TARGETS_PATH,
    ):
        content = path.read_text(encoding="utf-8")
        assert "# BEGIN SERVICE: authentik" in content
        assert "# END SERVICE: authentik" in content


def test_latency_slo_recording_rules_use_subqueries():
    catalog = generate_slo_rules.load_slo_catalog(generate_slo_rules.SLO_CATALOG_PATH)
    recording_payload = generate_slo_rules.build_recording_rules(catalog)

    latency_rules = {
        rule["record"]: rule["expr"]
        for rule in recording_payload["groups"][0]["rules"]
        if rule["record"].startswith("slo:openfga_latency:success_ratio_")
    }

    assert "[5m:])" in latency_rules["slo:openfga_latency:success_ratio_5m"]
    assert "[1h:])" in latency_rules["slo:openfga_latency:success_ratio_1h"]
    assert "[30d:])" in latency_rules["slo:openfga_latency:success_ratio_30d"]


def live_catalog():
    return generate_slo_rules.effective_catalog(generate_slo_rules.load_slo_catalog(generate_slo_rules.SLO_CATALOG_PATH))


def test_overlay_classifies_every_catalog_slo_exactly_once():
    catalog = generate_slo_rules.load_slo_catalog(generate_slo_rules.SLO_CATALOG_PATH)
    overlay = generate_slo_rules.load_slo_probe_overlay(catalog)
    endpoint_ids = [entry["slo_id"] for entry in overlay["endpoints"]]
    excluded_ids = [entry["slo_id"] for entry in overlay["excluded"]]

    assert sorted(endpoint_ids + excluded_ids) == sorted(slo["id"] for slo in catalog["slos"])
    assert len(set(endpoint_ids)) == len(endpoint_ids)
    assert all(entry["reason"].strip() for entry in overlay["excluded"])


def test_unclassified_catalog_slo_is_rejected():
    catalog = generate_slo_rules.load_slo_catalog(generate_slo_rules.SLO_CATALOG_PATH)
    overlay = generate_slo_rules.load_slo_probe_overlay(catalog)
    overlay["excluded"] = overlay["excluded"][1:]

    with pytest.raises(ValueError, match="unclassified"):
        slo_tracking.validate_slo_probe_overlay(overlay, catalog)


def test_generated_targets_have_no_placeholder_or_retired_addresses():
    targets = generate_slo_rules.build_targets(live_catalog())

    assert targets
    for target in targets:
        url = target["targets"][0]
        assert "example.com" not in url
        assert "10.10.10." not in url
        assert "100.64.0.1" not in url
        labels = target["labels"]
        if "probe_hostname" in labels:
            # edge endpoint: connect to the edge's private address, public name as Host/SNI
            assert url.startswith("https://{{ monitoring_slo_edge_connect_host }}/")
            assert labels["probe_hostname"].endswith(".{{ platform_domain }}")
            assert labels["display_url"].startswith(f"https://{labels['probe_hostname']}/")
        else:
            assert url.startswith("http://10.10.10.")


def test_only_fast_burn_pages_and_alerts_are_guarded_against_young_series():
    alert_payload = generate_slo_rules.build_alert_rules(live_catalog())
    rules = alert_payload["groups"][0]["rules"]

    assert rules
    for rule in rules:
        assert "count_over_time(" in rule["expr"], rule["alert"]
        expected = "critical" if rule["alert"].startswith("SLOFastBurn_") else "warning"
        assert rule["labels"]["severity"] == expected, rule["alert"]
        assert rule["for"] != "0m"


def test_recording_rules_only_report_series_that_are_still_probed():
    recording_payload = generate_slo_rules.build_recording_rules(live_catalog())
    success_rules = [
        rule for rule in recording_payload["groups"][0]["rules"] if ":success_ratio_" in rule["record"]
    ]

    assert success_rules
    for rule in success_rules:
        assert " and probe_" in rule["expr"], rule["record"]


def test_tls_targets_cover_only_edge_endpoints_with_21_and_7_day_policy():
    import generate_https_tls_assurance

    targets = generate_https_tls_assurance.discover_https_tls_targets()
    live_edge = [slo for slo in live_catalog()["slos"] if slo["tls_assurance"]]

    assert len(targets) == len({slo["target_url"].split("/")[2] for slo in live_edge})
    for target in targets:
        assert target["probe_hostname"].endswith(".{{ platform_domain }}")
        assert target["probe_url"].startswith("https://{{ monitoring_slo_edge_connect_host }}/")
        assert target["policy"] == {"unit": "days", "warn": 21, "critical": 7}
