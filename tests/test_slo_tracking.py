import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import generate_slo_rules  # noqa: E402
from slo_tracking import build_slo_status_entries, load_slo_catalog  # noqa: E402


def test_slo_catalog_loads_expected_entries() -> None:
    catalog = load_slo_catalog()
    assert len(catalog["slos"]) >= 9
    assert any(entry["indicator"] == "latency" for entry in catalog["slos"])
    assert any(entry["service_id"] == "homepage" for entry in catalog["slos"])


def test_generated_slo_assets_are_current() -> None:
    assert generate_slo_rules.outputs_match(load_slo_catalog())


def test_slo_status_entries_map_budget_to_health() -> None:
    def fake_query(expr: str) -> float:
        if expr.endswith(":budget_remaining"):
            return 0.62
        if expr.endswith(":burn_rate_1h"):
            return 0.8
        if expr.endswith(":time_to_budget_exhaustion_days"):
            return 23.4
        if ":success_ratio_" in expr:
            return 0.995
        raise AssertionError(expr)

    entries = build_slo_status_entries(query_fn=fake_query, prometheus_url="")
    assert entries
    assert entries[0]["metrics_available"] is True
    assert entries[0]["status"] == "healthy"
