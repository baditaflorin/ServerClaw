"""The Tier-0 replication alerts: shape, severities, and that monitoring_vm ships the file."""
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def _alerts():
    rules = yaml.safe_load((REPO / "config" / "prometheus" / "rules" / "tier0.yml").read_text(encoding="utf-8"))
    return {r["alert"]: r for g in rules["groups"] for r in g["rules"]}


def test_tier0_alerts_cover_stale_missing_replica_and_absent_metrics() -> None:
    alerts = _alerts()
    assert set(alerts) == {"Tier0SnapshotStale", "Tier0ReplicaMissing", "Tier0SnapshotMetricsAbsent", "Tier0CISnapshotStale", "Tier0CIReplicaMissing", "Tier0EscrowStale", "Tier0EscrowReplicaMissing", "Tier0EscrowMetricsAbsent", "DnsDriftDetected", "DnsDriftCheckStale", "Tier0GatewaySnapshotStale", "Tier0GatewayReplicaMissing", "GatewayCertExpiringSoon", "GatewayCertExpiryCritical", "GatewayCertFileMissing"}
    assert alerts["Tier0CISnapshotStale"]["labels"]["severity"] == "critical"
    assert alerts["Tier0SnapshotStale"]["labels"]["severity"] == "critical"
    assert "tier0_snapshot_last_success_timestamp_seconds" in alerts["Tier0SnapshotStale"]["expr"]
    assert "tier0_snapshot_replicas_total" in alerts["Tier0ReplicaMissing"]["expr"]
    for alert in alerts.values():
        assert alert["annotations"]["summary"] and alert["annotations"]["description"] and alert["annotations"]["runbook_url"]


def test_monitoring_vm_copies_the_tier0_rules() -> None:
    role = REPO / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "monitoring_vm"
    assert "monitoring_prometheus_tier0_rules_source_file" in (role / "defaults" / "main.yml").read_text(encoding="utf-8")
    assert "Copy the Tier-0 replication alert rules" in (role / "tasks" / "main.yml").read_text(encoding="utf-8")


def test_tier0_alerts_cover_the_key_escrow() -> None:
    alerts = _alerts()
    assert "tier0_escrow_last_success_timestamp_seconds" in alerts["Tier0EscrowStale"]["expr"]
    assert "tier0_escrow_replicas_total" in alerts["Tier0EscrowReplicaMissing"]["expr"]
    assert "absent(tier0_escrow_last_success_timestamp_seconds)" in alerts["Tier0EscrowMetricsAbsent"]["expr"]
