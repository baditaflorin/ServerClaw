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

    def test_render_portal_skips_nested_evidence_json_that_is_not_a_receipt(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="changelog-portal-evidence-test-"))
        receipts_dir = temp_dir / "receipts" / "live-applies"
        promotions_dir = temp_dir / "promotions"
        receipts_dir.mkdir(parents=True, exist_ok=True)
        promotions_dir.mkdir(parents=True, exist_ok=True)

        (receipts_dir / "2026-03-29-adr-0251-stage-smoke-live-apply.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "receipt_id": "2026-03-29-adr-0251-stage-smoke-live-apply",
                    "applied_on": "2026-03-29",
                    "recorded_on": "2026-03-29",
                    "recorded_by": "codex",
                    "source_commit": "abc1234",
                    "repo_version_context": "0.177.87",
                    "workflow_id": "converge-windmill",
                    "adr": "0251",
                    "summary": "Applied Windmill promotion gates on docker-runtime-lv3.",
                    "targets": [{"kind": "vm", "name": "docker-runtime-lv3"}],
                    "verification": [{"check": "gate-status", "result": "pass", "observed": "healthy"}],
                    "evidence_refs": ["docs/adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md"],
                    "notes": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (receipts_dir / "evidence" / "2026-03-29-adr-0251-gate-status-live.json").parent.mkdir(
            parents=True, exist_ok=True
        )
        (receipts_dir / "evidence" / "2026-03-29-adr-0251-gate-status-live.json").write_text(
            json.dumps(
                {
                    "status": "ok",
                    "result": {"status": "ok", "checks": [{"id": "post_merge_run", "status": "failed"}]},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        try:
            render_portal(
                temp_dir / "site",
                receipts_dir=receipts_dir,
                promotions_dir=promotions_dir,
                mutation_audit_file=REPO_ROOT / "tests" / "fixtures" / "mutation_audit_history.jsonl",
            )
            result = query_deployment_history(
                days=30,
                receipts_dir=receipts_dir,
                promotions_dir=promotions_dir,
                mutation_audit_file=REPO_ROOT / "tests" / "fixtures" / "mutation_audit_history.jsonl",
            )
            index_html = (temp_dir / "site" / "index.html").read_text(encoding="utf-8")
            live_entries = [entry for entry in result["entries"] if entry["change_type"] == "live-apply"]

            self.assertEqual(len(live_entries), 1)
            self.assertEqual(live_entries[0]["id"], "2026-03-29-adr-0251-stage-smoke-live-apply")
            self.assertIn("2026-03-29-adr-0251-stage-smoke-live-apply", index_html)
            self.assertNotIn("2026-03-29-adr-0251-gate-status-live", index_html)
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
