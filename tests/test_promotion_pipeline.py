import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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


def make_service(service_id: str, name: str, vm: str) -> dict:
    return {
        "id": service_id,
        "name": name,
        "vm": vm,
        "environments": {
            "production": {"status": "active", "url": f"https://{service_id}.lv3.org"},
            "staging": {"status": "active", "url": f"https://{service_id}.staging.lv3.org"},
        },
    }


class PromotionPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stage_ready_service = {
            "id": "grafana",
            "name": "Grafana",
            "vm": "monitoring-lv3",
            "environments": {
                "staging": {
                    "status": "active",
                    "url": "https://grafana.staging.lv3.org",
                    "stage_ready": True,
                    "smoke_suite_ids": ["staging-grafana-primary-path"],
                }
            },
        }
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
                    "check": "Grafana smoke",
                    "result": "pass",
                    "observed": "Smoke path ready.",
                }
            ],
            "smoke_suites": [
                {
                    "suite_id": "staging-grafana-primary-path",
                    "service_id": "grafana",
                    "environment": "staging",
                    "status": "passed",
                    "executed_at": "2026-03-23T09:05:00Z",
                    "summary": "1 passed, 0 failed, 0 skipped",
                    "report_ref": "docs/adr/0073-environment-promotion-gate-and-deployment-pipeline.md",
                }
            ],
            "evidence_refs": ["docs/adr/0073-environment-promotion-gate-and-deployment-pipeline.md"],
            "notes": [],
        }
        self.policy_patcher = patch.object(
            promotion_pipeline,
            "evaluate_promotion_gate_policy",
            side_effect=self._fake_policy_decision,
        )
        self.policy_patcher.start()
        self.vulnerability_patcher = patch.object(
            promotion_pipeline,
            "evaluate_service_vulnerability_gate",
            return_value={"approved": True, "reasons": [], "host": {}, "images": [], "profile": "edge-published"},
        )
        self.vulnerability_patcher.start()

    def tearDown(self) -> None:
        self.policy_patcher.stop()
        self.vulnerability_patcher.stop()

    def _fake_policy_decision(self, payload: dict, *, repo_root=None, toolchain=None) -> dict:
        reasons = list(payload["approval"]["reasons"])
        if payload["staging_receipt"]["age_hours"] > 24:
            reasons.append("staging receipt is older than 24 hours")
        if not payload["staging_receipt"]["verification_passed"]:
            reasons.append("staging receipt verification is not clean")
        reasons.extend(payload["smoke_gate"]["reasons"])
        if payload["blocking_findings"]["count"] > 0:
            reasons.append(f"open critical findings exist for service '{payload['service_id']}'")
        reasons.extend(payload["vulnerability_gate"]["reasons"])
        reasons.extend(payload["capacity_gate"]["reasons"])
        reasons.extend(payload["standby_gate"]["reasons"])
        if not payload["slo_gate"]["checked"]:
            reasons.append(f"SLO gate could not evaluate: {payload['slo_gate']['reason']}")
        elif payload["slo_gate"]["blocking_budget_messages"]:
            reasons.append(
                "SLO error budget below 10%: "
                + ", ".join(payload["slo_gate"]["blocking_budget_messages"])
            )
        return {
            "gate_decision": "approved" if not reasons else "rejected",
            "reasons": reasons,
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
                return_value={"grafana": self.stage_ready_service},
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
                promotion_pipeline, "load_capacity_model", return_value=object()
            ), patch.object(
                promotion_pipeline, "check_capacity_gate", return_value=(True, [])
            ), patch.object(
                promotion_pipeline,
                "evaluate_service_standby",
                return_value={"approved": True, "enforced": False, "tier": None, "reasons": [], "warnings": []},
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
                return_value={"grafana": self.stage_ready_service},
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
                promotion_pipeline, "load_capacity_model", return_value=object()
            ), patch.object(
                promotion_pipeline, "check_capacity_gate", return_value=(True, [])
            ), patch.object(
                promotion_pipeline,
                "evaluate_service_standby",
                return_value={"approved": True, "enforced": False, "tier": None, "reasons": [], "warnings": []},
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

    def test_evaluate_slo_gate_blocks_on_k6_budget_warning(self) -> None:
        entries = [
            {
                "id": "keycloak-availability",
                "service_id": "keycloak",
                "indicator": "availability",
                "metrics": {"budget_remaining": 0.75},
                "metrics_available": True,
                "metrics_error": None,
                "k6": {
                    "current_signal": {
                        "scenario": "load",
                        "receipt_path": "receipts/k6/load-keycloak-20260331T070000Z.json",
                        "result": "passed",
                        "error_budget_remaining_pct": 15.0,
                    },
                    "latest_receipts": {
                        "load": {
                            "scenario": "load",
                            "receipt_path": "receipts/k6/load-keycloak-20260331T070000Z.json",
                            "result": "passed",
                            "error_budget_remaining_pct": 15.0,
                        }
                    },
                },
            }
        ]

        with patch.object(promotion_pipeline, "build_slo_status_entries", return_value=entries):
            gate = promotion_pipeline.evaluate_slo_gate(prometheus_url="http://monitoring", service_id="keycloak")

        self.assertTrue(gate["checked"])
        self.assertIn(
            "latest k6 load receipt for keycloak shows 15.0% remaining (receipts/k6/load-keycloak-20260331T070000Z.json)",
            gate["blocking_messages"],
        )

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
                return_value={"grafana": self.stage_ready_service},
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
                promotion_pipeline, "load_capacity_model", return_value=object()
            ), patch.object(
                promotion_pipeline, "check_capacity_gate", return_value=(True, [])
            ), patch.object(
                promotion_pipeline,
                "evaluate_service_standby",
                return_value={"approved": True, "enforced": False, "tier": None, "reasons": [], "warnings": []},
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

    def test_gate_rejects_capacity_model_failure(self) -> None:
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
                return_value={"grafana": self.stage_ready_service},
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
                promotion_pipeline, "load_capacity_model", return_value=object()
            ), patch.object(
                promotion_pipeline,
                "check_capacity_gate",
                return_value=(False, ["projected RAM commitment 70.0 GB exceeds target 44.8 GB"]),
            ), patch.object(
                promotion_pipeline,
                "evaluate_service_standby",
                return_value={"approved": True, "enforced": False, "tier": None, "reasons": [], "warnings": []},
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
        self.assertFalse(verdict["capacity_gate"]["approved"])
        self.assertIn("projected RAM commitment 70.0 GB exceeds target 44.8 GB", verdict["reasons"])

    def test_gate_rejects_invalid_standby_policy(self) -> None:
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
                return_value={"postgres": make_service("postgres", "PostgreSQL", "postgres-lv3")},
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
                promotion_pipeline, "load_capacity_model", return_value=object()
            ), patch.object(
                promotion_pipeline, "check_capacity_gate", return_value=(True, [])
            ), patch.object(
                promotion_pipeline,
                "evaluate_service_standby",
                return_value={
                    "approved": False,
                    "enforced": True,
                    "tier": "R2",
                    "reasons": ["service 'postgres' primary and standby share namespace 'guest:postgres:patroni'"],
                    "warnings": [],
                },
            ), patch.object(
                promotion_pipeline, "evaluate_slo_gate", return_value={"checked": True, "entries": [], "blocking": [], "reason": None, "prometheus_url": "http://monitoring"}
            ), patch.object(
                promotion_pipeline.dt, "datetime", wraps=promotion_pipeline.dt.datetime
            ) as mocked_datetime:
                mocked_datetime.now.return_value = promotion_pipeline.dt.datetime(
                    2026, 3, 23, 12, 0, tzinfo=promotion_pipeline.dt.timezone.utc
                )
                verdict = promotion_pipeline.check_promotion_gate(
                    service_id="postgres",
                    staging_receipt_ref="receipts/live-applies/staging/receipt.json",
                    requester_class="human_operator",
                    approver_classes=["human_operator"],
                )

        self.assertEqual(verdict["gate_decision"], "rejected")
        self.assertFalse(verdict["standby_gate"]["approved"])
        self.assertIn("share namespace", " ".join(verdict["reasons"]))

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
                return_value={"grafana": self.stage_ready_service},
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
                promotion_pipeline, "load_capacity_model", return_value=object()
            ), patch.object(
                promotion_pipeline, "check_capacity_gate", return_value=(True, [])
            ), patch.object(
                promotion_pipeline,
                "evaluate_service_standby",
                return_value={"approved": True, "enforced": False, "tier": None, "reasons": [], "warnings": []},
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

    def test_gate_rejects_missing_required_stage_smoke_suite(self) -> None:
        from unittest.mock import patch

        missing_smoke_receipt = dict(self.stage_receipt)
        missing_smoke_receipt["smoke_suites"] = []
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
                return_value={"grafana": self.stage_ready_service},
            ), patch.object(
                promotion_pipeline, "load_receipt", return_value=missing_smoke_receipt
            ), patch.object(
                promotion_pipeline, "validate_receipt", return_value=None
            ), patch.object(
                promotion_pipeline, "resolve_receipt_path", return_value=stage_path
            ), patch.object(
                promotion_pipeline, "receipt_relative_path", return_value=Path("receipts/live-applies/staging/receipt.json")
            ), patch.object(
                promotion_pipeline, "load_findings", return_value=[]
            ), patch.object(
                promotion_pipeline, "load_capacity_model", return_value=object()
            ), patch.object(
                promotion_pipeline, "check_capacity_gate", return_value=(True, [])
            ), patch.object(
                promotion_pipeline,
                "evaluate_service_standby",
                return_value={"approved": True, "enforced": False, "tier": None, "reasons": [], "warnings": []},
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
        self.assertIn("staging smoke suites missing from staged receipt", " ".join(verdict["reasons"]))

    def test_gate_rejects_vulnerability_budget_failure(self) -> None:
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
                return_value={"windmill": {"id": "windmill", "name": "Windmill", "vm": "docker-runtime-lv3"}},
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
                "evaluate_service_vulnerability_gate",
                return_value={
                    "approved": False,
                    "reasons": ["image windmill_runtime has 3 critical findings, above the budget 0"],
                    "host": {},
                    "images": [],
                    "profile": "edge-published",
                },
            ), patch.object(
                promotion_pipeline, "load_capacity_model", return_value=object()
            ), patch.object(
                promotion_pipeline, "check_capacity_gate", return_value=(True, [])
            ), patch.object(
                promotion_pipeline,
                "evaluate_service_standby",
                return_value={"approved": True, "enforced": False, "tier": None, "reasons": [], "warnings": []},
            ), patch.object(
                promotion_pipeline,
                "evaluate_slo_gate",
                return_value={"checked": True, "entries": [], "blocking": [], "reason": None, "prometheus_url": "http://monitoring"},
            ), patch.object(
                promotion_pipeline.dt, "datetime", wraps=promotion_pipeline.dt.datetime
            ) as mocked_datetime:
                mocked_datetime.now.return_value = promotion_pipeline.dt.datetime(
                    2026, 3, 23, 12, 0, tzinfo=promotion_pipeline.dt.timezone.utc
                )
                verdict = promotion_pipeline.check_promotion_gate(
                    service_id="windmill",
                    staging_receipt_ref="receipts/live-applies/staging/receipt.json",
                    requester_class="human_operator",
                    approver_classes=["human_operator"],
                )

        self.assertEqual(verdict["gate_decision"], "rejected")
        self.assertIn("image windmill_runtime has 3 critical findings", " ".join(verdict["reasons"]))

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
                "stage_smoke_gate": {
                    "enforced": True,
                    "passed": True,
                    "required_suite_ids": ["staging-grafana-primary-path"],
                    "missing_suite_ids": [],
                    "failed_suite_ids": [],
                    "passed_suite_ids": ["staging-grafana-primary-path"],
                    "observed_suites": [
                        {
                            "suite_id": "staging-grafana-primary-path",
                            "service_id": "grafana",
                            "environment": "staging",
                            "status": "passed",
                            "summary": "1 passed, 0 failed, 0 skipped",
                        }
                    ],
                    "reasons": [],
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
