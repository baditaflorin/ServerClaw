import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from deployment_history import query_deployment_history  # noqa: E402
from generate_changelog_portal import render_portal  # noqa: E402


class ChangelogPortalTests(unittest.TestCase):
    def test_render_portal_writes_expected_pages(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="changelog-portal-test-"))
        promotions_dir = temp_dir / "promotions"
        promotions_dir.mkdir(parents=True, exist_ok=True)
        (promotions_dir / "promotion-1.json").write_text(
            json.dumps(
                {
                    "promotion_id": "promotion-1",
                    "branch": "codex/adr-0081-changelog-portal",
                    "playbook": "public-edge.yml",
                    "staging_receipt": "receipts/live-applies/2026-03-22-adr-0021-edge-publication-live-apply.json",
                    "staging_health_check": {"passed": True, "duration": "14m"},
                    "gate_decision": "approved",
                    "gate_actor": {"class": "operator", "id": "ops"},
                    "prod_receipt": "receipts/live-applies/2026-03-22-adr-0021-edge-publication-live-apply.json",
                    "ts": "2026-03-23T10:30:00Z",
                }
            ),
            encoding="utf-8",
        )
        try:
            render_portal(
                temp_dir / "site",
                receipts_dir=REPO_ROOT / "receipts" / "live-applies",
                promotions_dir=promotions_dir,
                mutation_audit_file=REPO_ROOT / "tests" / "fixtures" / "mutation_audit_history.jsonl",
            )
            index_html = (temp_dir / "site" / "index.html").read_text()
            promotions_html = (temp_dir / "site" / "promotions" / "index.html").read_text()
            grafana_html = (temp_dir / "site" / "service" / "grafana" / "index.html").read_text()

            self.assertIn("Deployment History Portal", index_html)
            self.assertIn("2026-03-22-adr-0011-monitoring-live-apply", index_html)
            self.assertIn('<meta name="robots" content="noindex, nofollow">', index_html)
            self.assertIn("promotion-1", promotions_html)
            self.assertIn("Grafana", grafana_html)
            self.assertIn("mutation-audit-log.md", grafana_html)
        finally:
            shutil.rmtree(temp_dir)

    def test_query_deployment_history_filters_by_service(self) -> None:
        result = query_deployment_history(
            service_id="grafana",
            days=30,
            mutation_audit_file=REPO_ROOT / "tests" / "fixtures" / "mutation_audit_history.jsonl",
        )
        self.assertGreaterEqual(result["count"], 2)
        self.assertTrue(all("grafana" in entry["service_ids"] for entry in result["entries"]))

    def test_query_deployment_history_ignores_live_apply_evidence_json(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="deployment-history-evidence-test-"))
        receipts_dir = temp_dir / "live-applies"
        promotions_dir = temp_dir / "promotions"
        evidence_dir = receipts_dir / "evidence"
        receipts_dir.mkdir(parents=True, exist_ok=True)
        promotions_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (receipts_dir / "2026-03-29-adr-9999-grafana-live-apply.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "receipt_id": "2026-03-29-adr-9999-grafana-live-apply",
                    "environment": "production",
                    "applied_on": "2026-03-29",
                    "recorded_on": "2026-03-29",
                    "recorded_by": "codex",
                    "source_commit": "8465168a90426723fad3083b78878575cff20534",
                    "repo_version_context": "0.80.0",
                    "workflow_id": "adr-9999-grafana-live-apply",
                    "adr": "9999",
                    "summary": "Grafana live apply.",
                    "targets": [{"kind": "service", "name": "grafana"}],
                    "verification": [{"check": "Smoke", "result": "pass", "observed": "Healthy."}],
                    "evidence_refs": ["docs/adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md"],
                    "notes": [],
                }
            ),
            encoding="utf-8",
        )
        (evidence_dir / "2026-03-29-adr-9999-grafana-smoke.json").write_text(
            json.dumps({"status": "ok", "service": "grafana"}),
            encoding="utf-8",
        )

        try:
            result = query_deployment_history(
                service_id="grafana",
                days=30,
                receipts_dir=receipts_dir,
                promotions_dir=promotions_dir,
                service_catalog={
                    "services": [
                        {
                            "id": "grafana",
                            "name": "Grafana",
                            "keywords": ["grafana"],
                        }
                    ]
                },
                mutation_audit_file=temp_dir / "missing-mutation-audit.jsonl",
            )
            self.assertEqual(result["count"], 1)
            self.assertEqual(result["entries"][0]["id"], "2026-03-29-adr-9999-grafana-live-apply")
        finally:
            shutil.rmtree(temp_dir)

    def test_cli_check_succeeds_without_loki_when_file_fixture_is_provided(self) -> None:
        process = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "generate_changelog_portal.py"),
                "--check",
                "--mutation-audit-file",
                str(REPO_ROOT / "tests" / "fixtures" / "mutation_audit_history.jsonl"),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)


if __name__ == "__main__":
    unittest.main()
