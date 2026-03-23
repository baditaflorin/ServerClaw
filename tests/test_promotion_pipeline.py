import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import promotion_pipeline  # noqa: E402


def make_catalog_context() -> tuple[dict, dict, dict]:
    workflow_catalog = {
        "workflows": {
            "deploy-and-promote": {
                "lifecycle_status": "active",
                "preferred_entrypoint": {"command": "make promote"},
            }
        }
    }
    command_catalog = {
        "approval_policies": {
            "operator_approved": {
                "allowed_requester_classes": ["human_operator", "agent"],
                "allowed_approver_classes": ["human_operator"],
                "minimum_approvals": 1,
                "require_preflight": True,
                "require_validation": True,
                "require_receipt_plan": True,
                "allow_self_approval": False,
                "allow_break_glass": False,
            }
        },
        "commands": {
            "promote-to-production": {
                "workflow_id": "deploy-and-promote",
                "approval_policy": "operator_approved",
                "evidence": {"live_apply_receipt_required": True},
            }
        },
    }
    return {}, workflow_catalog, command_catalog


class PromotionPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stage_receipt = {
            "schema_version": "1.0.0",
            "receipt_id": "2026-03-23-grafana-staging",
            "environment": "staging",
            "applied_on": "2026-03-23",
            "recorded_on": "2026-03-23",
            "recorded_at": "2026-03-23T09:00:00Z",
            "recorded_by": "codex",
            "source_commit": "deadbeef",
            "repo_version_context": "0.79.0",
            "workflow_id": "deploy-and-promote",
            "adr": "0073",
            "summary": "Staged grafana.",
            "targets": [{"kind": "guest", "name": "monitoring-lv3"}],
            "verification": [
                {
                    "check": "Grafana health",
                    "result": "pass",
                    "observed": "Ready.",
                }
            ],
            "evidence_refs": ["docs/adr/0073-environment-promotion-gate-and-deployment-pipeline.md"],
            "notes": [],
        }

    def test_gate_accepts_recent_clean_staging_receipt(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp_dir:
            stage_dir = Path(temp_dir) / "staging"
            stage_dir.mkdir(parents=True, exist_ok=True)
            stage_path = stage_dir / "receipt.json"
            stage_path.write_text("{}")

            with patch.object(promotion_pipeline, "STAGING_RECEIPTS_DIR", stage_dir), patch.object(
                promotion_pipeline, "load_catalog_context", return_value=make_catalog_context()
            ), patch.object(
                promotion_pipeline,
                "load_service_index",
                return_value={"grafana": {"id": "grafana", "name": "Grafana", "vm": "monitoring-lv3"}},
            ), patch.object(
                promotion_pipeline, "load_receipt", return_value=self.stage_receipt
            ), patch.object(
                promotion_pipeline, "validate_receipt", return_value=None
            ), patch.object(
                promotion_pipeline, "resolve_receipt_path", return_value=stage_path
            ), patch.object(
                promotion_pipeline, "receipt_relative_path", return_value=Path("receipts/live-applies/staging/receipt.json")
            ), patch.object(
                promotion_pipeline, "load_findings", return_value=[]
            ), patch.object(
                promotion_pipeline, "evaluate_slo_gate", return_value={"checked": True, "entries": [], "blocking": [], "reason": None, "prometheus_url": "http://monitoring"}
            ), patch.object(
                promotion_pipeline.dt, "datetime", wraps=promotion_pipeline.dt.datetime
            ) as mocked_datetime:
                mocked_datetime.now.return_value = promotion_pipeline.dt.datetime(
                    2026, 3, 23, 12, 0, tzinfo=promotion_pipeline.dt.timezone.utc
                )
                verdict = promotion_pipeline.check_promotion_gate(
                    service_id="grafana",
                    staging_receipt_ref="receipts/live-applies/staging/receipt.json",
                    requester_class="human_operator",
                    approver_classes=["human_operator"],
                )

        self.assertEqual(verdict["gate_decision"], "approved")
        self.assertTrue(verdict["staging_health_check"]["passed"])
        self.assertEqual(verdict["reasons"], [])

    def test_gate_rejects_stale_receipt(self) -> None:
        from unittest.mock import patch

        stale_receipt = dict(self.stage_receipt)
        stale_receipt["recorded_at"] = "2026-03-20T08:00:00Z"
        with tempfile.TemporaryDirectory() as temp_dir:
            stage_dir = Path(temp_dir) / "staging"
            stage_dir.mkdir(parents=True, exist_ok=True)
            stage_path = stage_dir / "receipt.json"
            stage_path.write_text("{}")

            with patch.object(promotion_pipeline, "STAGING_RECEIPTS_DIR", stage_dir), patch.object(
                promotion_pipeline, "load_catalog_context", return_value=make_catalog_context()
            ), patch.object(
                promotion_pipeline,
                "load_service_index",
                return_value={"grafana": {"id": "grafana", "name": "Grafana", "vm": "monitoring-lv3"}},
            ), patch.object(
                promotion_pipeline, "load_receipt", return_value=stale_receipt
            ), patch.object(
                promotion_pipeline, "validate_receipt", return_value=None
            ), patch.object(
                promotion_pipeline, "resolve_receipt_path", return_value=stage_path
            ), patch.object(
                promotion_pipeline, "receipt_relative_path", return_value=Path("receipts/live-applies/staging/receipt.json")
            ), patch.object(
                promotion_pipeline, "load_findings", return_value=[]
            ), patch.object(
                promotion_pipeline, "evaluate_slo_gate", return_value={"checked": True, "entries": [], "blocking": [], "reason": None, "prometheus_url": "http://monitoring"}
            ), patch.object(
                promotion_pipeline.dt, "datetime", wraps=promotion_pipeline.dt.datetime
            ) as mocked_datetime:
                mocked_datetime.now.return_value = promotion_pipeline.dt.datetime(
                    2026, 3, 23, 12, 0, tzinfo=promotion_pipeline.dt.timezone.utc
                )
                verdict = promotion_pipeline.check_promotion_gate(
                    service_id="grafana",
                    staging_receipt_ref="receipts/live-applies/staging/receipt.json",
                    requester_class="human_operator",
                    approver_classes=["human_operator"],
                )

        self.assertEqual(verdict["gate_decision"], "rejected")
        self.assertIn("staging receipt is older than 24 hours", verdict["reasons"])

    def test_gate_rejects_critical_findings_for_service(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp_dir:
            stage_dir = Path(temp_dir) / "staging"
            stage_dir.mkdir(parents=True, exist_ok=True)
            stage_path = stage_dir / "receipt.json"
            stage_path.write_text("{}")

            with patch.object(promotion_pipeline, "STAGING_RECEIPTS_DIR", stage_dir), patch.object(
                promotion_pipeline, "load_catalog_context", return_value=make_catalog_context()
            ), patch.object(
                promotion_pipeline,
                "load_service_index",
                return_value={"grafana": {"id": "grafana", "name": "Grafana", "vm": "monitoring-lv3"}},
            ), patch.object(
                promotion_pipeline, "load_receipt", return_value=self.stage_receipt
            ), patch.object(
                promotion_pipeline, "validate_receipt", return_value=None
            ), patch.object(
                promotion_pipeline, "resolve_receipt_path", return_value=stage_path
            ), patch.object(
                promotion_pipeline, "receipt_relative_path", return_value=Path("receipts/live-applies/staging/receipt.json")
            ), patch.object(
                promotion_pipeline,
                "load_findings",
                return_value=[{"severity": "critical", "summary": "Grafana probe failed", "details": []}],
            ), patch.object(
                promotion_pipeline, "evaluate_slo_gate", return_value={"checked": True, "entries": [], "blocking": [], "reason": None, "prometheus_url": "http://monitoring"}
            ), patch.object(
                promotion_pipeline.dt, "datetime", wraps=promotion_pipeline.dt.datetime
            ) as mocked_datetime:
                mocked_datetime.now.return_value = promotion_pipeline.dt.datetime(
                    2026, 3, 23, 12, 0, tzinfo=promotion_pipeline.dt.timezone.utc
                )
                verdict = promotion_pipeline.check_promotion_gate(
                    service_id="grafana",
                    staging_receipt_ref="receipts/live-applies/staging/receipt.json",
                    requester_class="human_operator",
                    approver_classes=["human_operator"],
                )

        self.assertEqual(verdict["gate_decision"], "rejected")
        self.assertIn("open critical findings exist for service 'grafana'", verdict["reasons"])

    def test_gate_rejects_low_slo_budget(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp_dir:
            stage_dir = Path(temp_dir) / "staging"
            stage_dir.mkdir(parents=True, exist_ok=True)
            stage_path = stage_dir / "receipt.json"
            stage_path.write_text("{}")

            with patch.object(promotion_pipeline, "STAGING_RECEIPTS_DIR", stage_dir), patch.object(
                promotion_pipeline, "load_catalog_context", return_value=make_catalog_context()
            ), patch.object(
                promotion_pipeline,
                "load_service_index",
                return_value={"grafana": {"id": "grafana", "name": "Grafana", "vm": "monitoring-lv3"}},
            ), patch.object(
                promotion_pipeline, "load_receipt", return_value=self.stage_receipt
            ), patch.object(
                promotion_pipeline, "validate_receipt", return_value=None
            ), patch.object(
                promotion_pipeline, "resolve_receipt_path", return_value=stage_path
            ), patch.object(
                promotion_pipeline, "receipt_relative_path", return_value=Path("receipts/live-applies/staging/receipt.json")
            ), patch.object(
                promotion_pipeline, "load_findings", return_value=[]
            ), patch.object(
                promotion_pipeline,
                "evaluate_slo_gate",
                return_value={
                    "checked": True,
                    "entries": [{"id": "grafana-availability", "metrics": {"budget_remaining": 0.04}}],
                    "blocking": [{"id": "grafana-availability", "metrics": {"budget_remaining": 0.04}}],
                    "reason": None,
                    "prometheus_url": "http://monitoring",
                },
            ), patch.object(
                promotion_pipeline.dt, "datetime", wraps=promotion_pipeline.dt.datetime
            ) as mocked_datetime:
                mocked_datetime.now.return_value = promotion_pipeline.dt.datetime(
                    2026, 3, 23, 12, 0, tzinfo=promotion_pipeline.dt.timezone.utc
                )
                verdict = promotion_pipeline.check_promotion_gate(
                    service_id="grafana",
                    staging_receipt_ref="receipts/live-applies/staging/receipt.json",
                    requester_class="human_operator",
                    approver_classes=["human_operator"],
                )

        self.assertEqual(verdict["gate_decision"], "rejected")
        self.assertIn("SLO error budget below 10%", verdict["reasons"][0] + " ".join(verdict["reasons"]))

    def test_validate_promotion_receipt_accepts_linked_receipts(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            promotion_path = temp_root / "tmp-promotion.json"
            staging_path = temp_root / "tmp-stage-linked.json"
            prod_path = temp_root / "tmp-prod-linked.json"
            staging_path.write_text("{}")
            prod_path.write_text("{}")

            receipt = {
                "schema_version": "1.0.0",
                "promotion_id": "tmp-promotion",
                "branch": "codex/adr-0073-promotion-pipeline",
                "service": "grafana",
                "playbook": "grafana",
                "staging_receipt": "receipts/live-applies/staging/tmp-stage-linked.json",
                "staging_health_check": {
                    "passed": True,
                    "checks": [
                        {
                            "check": "Grafana health",
                            "result": "pass",
                            "passed": True,
                            "observed": "Ready.",
                        }
                    ],
                },
                "gate_decision": "approved",
                "gate_actor": {"class": "operator", "id": "ops"},
                "prod_receipt": "receipts/live-applies/tmp-prod-linked.json",
                "repo_version_context": "0.79.0",
                "platform_version_context": "0.37.0",
                "ts": "2026-03-23T12:00:00Z",
                "notes": ["ok"],
            }

            def resolve(ref: str) -> Path:
                if "staging" in ref:
                    return staging_path
                return prod_path

            with patch.object(promotion_pipeline, "resolve_receipt_path", side_effect=resolve):
                promotion_pipeline.validate_promotion_receipt(receipt, promotion_path)

    def test_promote_service_dry_run_returns_summary(self) -> None:
        from unittest.mock import patch

        gate_verdict = {
            "gate_decision": "approved",
            "staging_receipt": "receipts/live-applies/staging/example.json",
            "staging_health_check": {"passed": True, "checks": []},
            "reasons": [],
        }

        with patch.object(promotion_pipeline, "current_branch", return_value="codex/adr-0073-promotion-pipeline"), patch.object(
            promotion_pipeline, "run_make", return_value={"command": "make validate", "returncode": 0, "stdout": "", "stderr": ""}
        ), patch.object(
            promotion_pipeline, "check_promotion_gate", return_value=gate_verdict
        ):
            result = promotion_pipeline.promote_service(
                service_id="grafana",
                staging_receipt_ref="receipts/live-applies/staging/example.json",
                branch=None,
                requester_class="human_operator",
                approver_classes=["human_operator"],
                extra_args="",
                dry_run=True,
            )

        self.assertEqual(result["status"], "dry-run")
        self.assertEqual(result["service"], "grafana")
        self.assertEqual(result["gate"]["gate_decision"], "approved")

    def test_deployment_order_sorts_dependencies_first(self) -> None:
        graph = promotion_pipeline.load_dependency_graph(
            promotion_pipeline.DEPENDENCY_GRAPH_PATH,
            service_catalog_path=promotion_pipeline.SERVICE_CATALOG_PATH,
            validate_schema=False,
        )

        ordered = promotion_pipeline.deployment_order(["ops_portal", "postgres", "keycloak"], graph)

        self.assertEqual(ordered, ["postgres", "keycloak", "ops_portal"])


if __name__ == "__main__":
    unittest.main()
