"""ADR 0443 — tests for topology drift detection.

Covers:
- topology_reconciler.build_expected
- topology_reconciler.diff (missing / misplaced / unexpected)
- topology_reconciler.write_reports
- validate_no_hardcoded_topology.scan (strong + heuristic + allowlist)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import topology_reconciler as rec
from scripts import validate_no_hardcoded_topology as lint


# ---------------------------------------------------------------------------
# topology_reconciler
# ---------------------------------------------------------------------------


def _registry():
    return {
        "keycloak": {"host_group": "runtime-control", "internal_port": 8091, "container_name": "keycloak"},
        "outline": {"host_group": "docker-runtime", "internal_port": 3006, "container_name": "outline"},
        "no_port": {"host_group": "runtime-control", "internal_port": None},
    }


def test_build_expected_groups_by_host():
    expected = rec.build_expected(["keycloak", "outline"], _registry())
    assert set(expected.keys()) == {"runtime-control", "docker-runtime"}
    assert expected["runtime-control"][0].name == "keycloak"
    assert expected["runtime-control"][0].internal_port == 8091
    assert expected["docker-runtime"][0].internal_port == 3006


def test_build_expected_skips_unknown_services():
    expected = rec.build_expected(["nonsense"], _registry())
    assert expected == {}


def test_diff_clean_when_reality_matches():
    expected = rec.build_expected(["keycloak"], _registry())
    probes = {
        "runtime-control": {
            "containers": [{"name": "keycloak", "image": "kc:1"}],
            "listening_tcp": [{"port": 8091, "address": "0.0.0.0"}],
        }
    }
    drifts = rec.diff(expected, probes, all_known_services={"keycloak"})
    assert drifts == []


def test_diff_flags_missing_service():
    expected = rec.build_expected(["keycloak"], _registry())
    probes = {
        "runtime-control": {
            "containers": [],
            "listening_tcp": [],
        }
    }
    drifts = rec.diff(expected, probes, all_known_services={"keycloak"})
    severities = [d.severity for d in drifts]
    assert "missing" in severities
    missing = next(d for d in drifts if d.severity == "missing" and d.service == "keycloak")
    assert "keycloak" in missing.detail


def test_diff_flags_misplaced_service():
    expected = rec.build_expected(["keycloak"], _registry())
    # Keycloak is running on docker-runtime, not on runtime-control.
    probes = {
        "runtime-control": {"containers": [], "listening_tcp": []},
        "docker-runtime": {
            "containers": [{"name": "keycloak", "image": "kc:1"}],
            "listening_tcp": [{"port": 8091, "address": "0.0.0.0"}],
        },
    }
    drifts = rec.diff(expected, probes, all_known_services={"keycloak"})
    misplaced = [d for d in drifts if d.severity == "misplaced"]
    assert misplaced, f"expected misplaced drift, got: {[d.severity for d in drifts]}"
    assert misplaced[0].service == "keycloak"
    assert misplaced[0].host == "docker-runtime"


def test_diff_flags_unexpected_container():
    expected = rec.build_expected(["keycloak"], _registry())
    probes = {
        "runtime-control": {
            "containers": [
                {"name": "keycloak"},
                {"name": "rogue", "image": "rogue:1"},
            ],
            "listening_tcp": [{"port": 8091}],
        }
    }
    drifts = rec.diff(expected, probes, all_known_services={"keycloak"})
    unexpected = [d for d in drifts if d.severity == "unexpected"]
    assert any("rogue" in (d.observed or {}).get("container", "") for d in unexpected)


def test_diff_no_probe_data_emits_missing_drift():
    expected = rec.build_expected(["keycloak"], _registry())
    drifts = rec.diff(expected, {"runtime-control": None}, all_known_services={"keycloak"})
    assert any(d.severity == "missing" and d.service is None for d in drifts)


def test_write_reports_creates_json_and_md(tmp_path: Path):
    expected = rec.build_expected(["keycloak"], _registry())
    probes = {
        "runtime-control": {
            "containers": [{"name": "keycloak"}],
            "listening_tcp": [{"port": 8091}],
        }
    }
    drifts = rec.diff(expected, probes, all_known_services={"keycloak"})
    json_path, md_path = rec.write_reports(
        deployment_slug="testdep",
        state_dir=tmp_path,
        expected=expected,
        probes=probes,
        drifts=drifts,
    )
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text())
    assert payload["schema"] == rec.DRIFT_SCHEMA
    assert payload["deployment"] == "testdep"
    assert payload["drift_count"] == 0
    assert "Topology Drift Report" in md_path.read_text()


# ---------------------------------------------------------------------------
# validate_no_hardcoded_topology
# ---------------------------------------------------------------------------


def _seed_repo(tmp_path: Path) -> Path:
    """Create a minimal repo layout for the linter to scan."""
    (tmp_path / "inventory" / "host_vars").mkdir(parents=True)
    (tmp_path / "inventory" / "group_vars" / "all").mkdir(parents=True)

    # proxmox_guests fixture
    (tmp_path / "inventory" / "host_vars" / "proxmox-host.yml").write_text(
        "proxmox_guests:\n"
        "  - name: runtime-control\n"
        "    vmid: 192\n"
        "    ipv4: 10.10.10.92\n"
        "  - name: docker-runtime\n"
        "    vmid: 120\n"
        "    ipv4: 10.10.10.20\n"
    )
    # service registry fixture
    (tmp_path / "inventory" / "group_vars" / "all" / "platform_services.yml").write_text(
        "platform_service_registry:\n"
        "  keycloak:\n"
        "    host_group: runtime-control\n"
        "    internal_port: 8091\n"
        "  outline:\n"
        "    host_group: docker-runtime\n"
        "    internal_port: 3006\n"
    )
    return tmp_path


def test_linter_clean_repo(tmp_path: Path):
    _seed_repo(tmp_path)
    findings = lint.scan(tmp_path)
    assert findings == []


def test_linter_flags_strong_ip_port(tmp_path: Path):
    _seed_repo(tmp_path)
    bad = tmp_path / "roles" / "fake" / "templates" / "config.j2"
    bad.parent.mkdir(parents=True)
    bad.write_text("upstream backend { server 10.10.10.92:8091; }\n")
    findings = lint.scan(tmp_path)
    strong = [f for f in findings if f.rule == "strong"]
    assert strong, f"expected strong finding, got: {findings}"
    assert strong[0].matched == "10.10.10.92:8091"
    assert strong[0].service == "keycloak"


def test_linter_flags_heuristic_bare_ip_with_service_name(tmp_path: Path):
    _seed_repo(tmp_path)
    bad = tmp_path / "roles" / "fake" / "tasks" / "main.yml"
    bad.parent.mkdir(parents=True)
    bad.write_text("# point keycloak at 10.10.10.92 directly\n")
    findings = lint.scan(tmp_path)
    heuristic = [f for f in findings if f.rule == "heuristic"]
    assert heuristic
    assert heuristic[0].matched == "10.10.10.92"
    assert heuristic[0].service == "keycloak"


def test_linter_skips_allowlisted_dirs(tmp_path: Path):
    _seed_repo(tmp_path)
    for sub in ("docs", "tests", "build", ".local", "receipts"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        (tmp_path / sub / "x.yml").write_text("server: 10.10.10.92:8091  # keycloak\n")
    findings = lint.scan(tmp_path)
    assert findings == [], f"allowlisted paths leaked findings: {findings}"


def test_linter_skips_inventory_host_vars(tmp_path: Path):
    _seed_repo(tmp_path)
    # An additional host_vars file that does include the IP — this is the
    # operator-authored topology source and must not be flagged.
    (tmp_path / "inventory" / "host_vars" / "extra.yml").write_text("service_endpoint: 10.10.10.92:8091  # keycloak\n")
    findings = lint.scan(tmp_path)
    assert findings == []


def test_linter_does_not_match_unrelated_ports(tmp_path: Path):
    _seed_repo(tmp_path)
    bad = tmp_path / "scripts" / "thing.py"
    bad.parent.mkdir(parents=True)
    # Different port — does NOT correspond to any service mapping.
    bad.write_text("URL = 'http://10.10.10.92:99999'  # bogus port, no service\n")
    findings = lint.scan(tmp_path)
    strong = [f for f in findings if f.rule == "strong"]
    assert strong == []


def test_linter_noqa_marker_suppresses_finding(tmp_path: Path):
    _seed_repo(tmp_path)
    bad = tmp_path / "scripts" / "thing.py"
    bad.parent.mkdir(parents=True)
    bad.write_text(
        "# real drift\nURL = 'http://10.10.10.92:8091'  # keycloak\n"
        "# legitimate default\nFB = 'http://10.10.10.92:8091'  # keycloak  # noqa: topology-hardcode\n"
    )
    findings = lint.scan(tmp_path)
    # Only the first occurrence (without the noqa marker) should fire.
    matched_lines = sorted(f.line for f in findings)
    assert matched_lines == [2], f"unexpected: {findings}"


def test_windmill_wrapper_receipt_translation(tmp_path: Path):
    """The Windmill wrapper's _publish_ops_portal_receipt converts a
    topology drift-report into the ops-portal records schema."""
    import importlib.util

    wrapper_path = REPO_ROOT / "config" / "windmill" / "scripts" / "topology-drift-check.py"
    spec = importlib.util.spec_from_file_location("topology_drift_check_wrapper", wrapper_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    report = {
        "schema": "drift-report/v1",
        "deployment": "0fork",
        "captured_at": "2026-04-27T11:00:00Z",
        "drift_count": 2,
        "drifts": [
            {"severity": "missing", "host": "runtime-control", "service": "keycloak", "detail": "container missing"},
            {"severity": "unexpected", "host": "docker-runtime", "service": None, "detail": "rogue container"},
        ],
    }
    payload = {
        "status": "drift",
        "drift_count": 2,
        "deployment": "0fork",
        "report_path": "/some/path/drift-report.json",
    }
    receipt_path = mod._publish_ops_portal_receipt(tmp_path, report, payload)
    assert receipt_path is not None
    assert receipt_path.exists()
    receipt = json.loads(receipt_path.read_text())
    assert receipt["schema"] == "ops-portal-drift-receipt/v1"
    assert receipt["summary"]["status"] == "drift"
    assert receipt["summary"]["drift_count"] == 2
    severities = sorted(r["severity"] for r in receipt["records"])
    assert severities == ["critical", "warn"]
    sources = {r["source"] for r in receipt["records"]}
    assert sources == {"topology-reconciler"}


def test_linter_negative_lookaround_prevents_overmatch(tmp_path: Path):
    """10.10.10.10 must not greedy-match into 10.10.10.100."""
    (tmp_path / "inventory" / "host_vars").mkdir(parents=True)
    (tmp_path / "inventory" / "group_vars" / "all").mkdir(parents=True)
    (tmp_path / "inventory" / "host_vars" / "proxmox-host.yml").write_text(
        "proxmox_guests:\n  - name: nginx\n    vmid: 110\n    ipv4: 10.10.10.10\n"
    )
    (tmp_path / "inventory" / "group_vars" / "all" / "platform_services.yml").write_text(
        "platform_service_registry:\n  nginx_runtime:\n    host_group: nginx\n    internal_port: 80\n"
    )
    bad = tmp_path / "scripts" / "thing.py"
    bad.parent.mkdir(parents=True)
    bad.write_text("# unrelated address: 10.10.10.100:80\n")
    findings = lint.scan(tmp_path)
    assert findings == [], f"over-matched: {findings}"
