"""The Tier-0 replication alerts: shape, severities, and that monitoring_vm ships the file."""
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def _alerts():
    rules = yaml.safe_load((REPO / "config" / "prometheus" / "rules" / "tier0.yml").read_text(encoding="utf-8"))
    return {r["alert"]: r for g in rules["groups"] for r in g["rules"]}


def test_tier0_alerts_cover_stale_missing_replica_and_absent_metrics() -> None:
    alerts = _alerts()
    assert set(alerts) == {"Tier0SnapshotStale", "Tier0ReplicaMissing", "Tier0SnapshotMetricsAbsent", "Tier0CISnapshotStale", "Tier0CIReplicaMissing", "Tier0EscrowStale", "Tier0EscrowReplicaMissing", "Tier0EscrowMetricsAbsent", "DnsDriftDetected", "DnsDriftCheckStale", "Tier0GatewaySnapshotStale", "Tier0GatewayReplicaMissing", "GatewayCertExpiringSoon", "GatewayCertExpiryCritical", "GatewayCertFileMissing", "ServedCertExpiringSoon", "ServedCertExpiryCritical", "ServedCertDoesNotCoverHost", "ServedCertProbeFailing", "ServedCertProbeStale", "Tier0FailoverRehearsalStale", "Tier0FullFailoverRehearsalStale", "Tier0FailoverRehearsalNeverRecorded", "Tier0StandbyImagesMissing", "Tier0DomainscopeSnapshotStale", "Tier0DomainscopeReplicaMissing", "Tier0DomainscopeSnapshotMissing", "Tier0SliceRefreshFailed", "Tier0SliceRefreshStale", "Tier0SliceRefreshMissing", "Tier0SliceSyncStale", "Tier0SliceImagesMissing", "Tier0EdgeGrantsFailed", "Tier0EdgeGrantsStale", "Tier0EdgeGrantsMissing", "Tier0EdgeGrantsNeedHuman", "Tier0EdgeGrantsPrStuck", "Tier0EdgeGrantsInstalledDrift"}
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


def test_tier0_alerts_cover_the_daily_slice_refresh() -> None:
    alerts = _alerts()
    assert "max(tier0_slice_refresh_ok) == 0" in alerts["Tier0SliceRefreshFailed"]["expr"]
    assert "tier0_slice_refresh_last_success_timestamp_seconds" in alerts["Tier0SliceRefreshStale"]["expr"]
    assert "absent(tier0_slice_refresh_last_success_timestamp_seconds)" in alerts["Tier0SliceRefreshMissing"]["expr"]
    assert all(alerts[a]["labels"]["severity"] == "warning" for a in ("Tier0SliceRefreshFailed", "Tier0SliceRefreshStale", "Tier0SliceRefreshMissing"))


def test_tier0_alerts_cover_the_slice_sync_that_used_to_fail_silently() -> None:
    alerts = _alerts()
    assert "tier0_slice_last_success_timestamp_seconds" in alerts["Tier0SliceSyncStale"]["expr"]
    assert "tier0_slice_images_missing_on_standby" in alerts["Tier0SliceImagesMissing"]["expr"]
    assert alerts["Tier0SliceSyncStale"]["labels"]["severity"] == "warning"
    assert "04:10 UTC" in alerts["Tier0SliceSyncStale"]["annotations"]["description"]


def test_tier0_alerts_cover_the_unattended_standby_edge_grants_job() -> None:
    alerts = _alerts()
    assert alerts["Tier0EdgeGrantsFailed"]["expr"] == "max(tier0_edge_grants_ok) == 0"
    assert "tier0_edge_grants_last_run_timestamp_seconds" in alerts["Tier0EdgeGrantsStale"]["expr"]
    assert "absent(tier0_edge_grants_last_run_timestamp_seconds)" in alerts["Tier0EdgeGrantsMissing"]["expr"]
    for name in ("capped", "rejected_pairs", "unverified_pairs", "already_granted_pairs"):
        assert "tier0_edge_grants_" + name in alerts["Tier0EdgeGrantsNeedHuman"]["expr"]
    assert alerts["Tier0EdgeGrantsPrStuck"]["expr"] == "max(tier0_edge_grants_pr_open) == 1"
    assert alerts["Tier0EdgeGrantsInstalledDrift"]["expr"] == "max(tier0_edge_grants_installed_matches_git) == 0" and alerts["Tier0EdgeGrantsInstalledDrift"]["for"] == "3h"


def test_the_alert_metrics_are_the_ones_the_job_writes() -> None:
    import re
    job = (REPO / "scripts" / "standby_edge_grants_job.py").read_text(encoding="utf-8")
    written = {"tier0_edge_grants_" + m.group(1) for m in re.finditer(r'"([a-z_]+)": (?:now|1|0|st\.get|prev)|\b([a-z_]+)=', job) if m.group(1)}
    written |= {"tier0_edge_grants_" + k for k in ("ok", "last_run_timestamp_seconds", "last_success_timestamp_seconds", "capped", "rejected_pairs", "unverified_pairs", "already_granted_pairs", "pr_open", "installed_matches_git")}
    used = set(re.findall(r"tier0_edge_grants_\w+", " ".join(a["expr"] for n, a in _alerts().items() if n.startswith("Tier0EdgeGrants"))))
    assert used and used <= written, used - written
    for key in ("last_run_timestamp_seconds", "ok", "capped", "rejected_pairs", "unverified_pairs", "already_granted_pairs", "pr_open", "installed_matches_git"):
        assert '"%s"' % key in job                                                                          # each metric an alert reads really is a key the job sets
