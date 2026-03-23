import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import generate_ops_portal as ops_portal  # noqa: E402
from service_catalog import load_service_catalog, validate_service_catalog  # noqa: E402


class ServiceCatalogTests(unittest.TestCase):
    def test_catalog_validates(self) -> None:
        catalog = load_service_catalog()
        validate_service_catalog(catalog)
        self.assertGreaterEqual(len(catalog["services"]), 12)


class OpsPortalRenderTests(unittest.TestCase):
    def test_render_portal_writes_expected_pages(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="ops-portal-test-"))
        original_receipts = ops_portal.active_ephemeral_receipts
        original_release_snapshot = ops_portal.build_release_status_snapshot
        snapshot_file = temp_dir / "ops-portal-snapshot.html"
        try:
            ops_portal.active_ephemeral_receipts = lambda: [
                {
                    "vm_id": 910,
                    "fixture_id": "ops-base",
                    "owner": "codex",
                    "purpose": "adr-0106-test",
                    "expires_at": "2026-03-24T00:00:00Z",
                    "status": "active",
                }
            ]
            ops_portal.build_release_status_snapshot = lambda timeout=0.5: {
                "repo_version": "0.104.0",
                "platform_version": "0.40.0",
                "release_blockers": {"detail": "0 workstreams in progress"},
                "summary": {"ready": False, "met": 1, "total": 6, "percent": 16.67},
                "criteria": [
                    {
                        "label": "ADR window 0001-0111",
                        "status": "pending",
                        "detail": "89/111 implemented",
                        "met": False,
                    }
                ],
            }
            ops_portal.render_portal(
                temp_dir,
                REPO_ROOT / "tests" / "fixtures" / "ops_portal_health.json",
                0,
                snapshot_file,
            )
            index_html = (temp_dir / "index.html").read_text()
            dns_html = (temp_dir / "subdomains" / "index.html").read_text()
            agents_html = (temp_dir / "agents" / "index.html").read_text()

            self.assertIn("Platform Operations Portal", index_html)
            self.assertIn("Release Readiness", index_html)
            self.assertIn("Grafana", index_html)
            self.assertIn("healthy", index_html)
            self.assertIn("Drift Status", index_html)
            self.assertIn("Ephemeral VMs", index_html)
            self.assertIn("adr-0106-test", index_html)
            self.assertIn("ops.lv3.org", dns_html)
            self.assertIn("get-platform-status", agents_html)
            self.assertEqual(snapshot_file.read_text(), index_html)
        finally:
            ops_portal.active_ephemeral_receipts = original_receipts
            ops_portal.build_release_status_snapshot = original_release_snapshot
            shutil.rmtree(temp_dir)

    def test_render_portal_includes_drift_receipt_summary(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="ops-portal-test-"))
        original = ops_portal.latest_drift_report
        try:
            drift_receipt = temp_dir / "latest-drift.json"
            drift_receipt.write_text(
                '{"generated_at":"2026-03-23T18:00:00Z","summary":{"status":"warn","unsuppressed_count":1,"warn_count":1,"critical_count":0,"suppressed_count":0},"records":[{"source":"dns","service":"grafana","severity":"warn","detail":"wrong record"}]}'
            )
            ops_portal.latest_drift_report = lambda: (drift_receipt, json.loads(drift_receipt.read_text()))
            ops_portal.render_portal(
                temp_dir,
                REPO_ROOT / "tests" / "fixtures" / "ops_portal_health.json",
                0,
                temp_dir / "snapshot.html",
            )
            index_html = (temp_dir / "index.html").read_text()
            self.assertIn("Latest Receipt", index_html)
            self.assertIn("wrong record", index_html)
        finally:
            ops_portal.latest_drift_report = original
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
