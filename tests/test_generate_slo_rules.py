from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_slo_rules


def test_generated_payloads_include_fast_and_slow_burn_alerts():
    catalog = generate_slo_rules.load_slo_catalog(generate_slo_rules.SLO_CATALOG_PATH)
    recording_payload = generate_slo_rules.build_recording_rules(catalog)
    alert_payload = generate_slo_rules.build_alert_rules(catalog)

    assert recording_payload["groups"][0]["name"] == "slo_recording_rules"
    alert_names = {rule["alert"] for rule in alert_payload["groups"][0]["rules"]}
    assert "SLOFastBurn_keycloak_availability" in alert_names
    assert "SLOSlowBurn_keycloak_availability" in alert_names


def test_latency_slo_recording_rules_use_subqueries():
    catalog = generate_slo_rules.load_slo_catalog(generate_slo_rules.SLO_CATALOG_PATH)
    recording_payload = generate_slo_rules.build_recording_rules(catalog)

    latency_rules = {
        rule["record"]: rule["expr"]
        for rule in recording_payload["groups"][0]["rules"]
        if rule["record"].startswith("slo:keycloak_latency:success_ratio_")
    }

    assert latency_rules["slo:keycloak_latency:success_ratio_5m"].endswith("[5m:])")
    assert latency_rules["slo:keycloak_latency:success_ratio_1h"].endswith("[1h:])")
    assert latency_rules["slo:keycloak_latency:success_ratio_30d"].endswith("[30d:])")
