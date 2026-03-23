import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "agent_tool_registry.py"


class AgentToolRegistryTests(unittest.TestCase):
    maxDiff = None

    def run_registry(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=merged_env,
        )

    def run_registry_with_pyyaml(
        self,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            ["uvx", "--from", "pyyaml", "python", str(SCRIPT_PATH), *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=merged_env,
        )

    def read_audit_events(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_validate_registry(self) -> None:
        process = self.run_registry("--validate")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("Agent tool registry OK", process.stdout)

    def test_export_mcp_tools(self) -> None:
        process = self.run_registry("--export-mcp")
        self.assertEqual(process.returncode, 0, process.stderr)
        payload = json.loads(process.stdout)
        tool_names = {tool["name"] for tool in payload["tools"]}
        self.assertGreaterEqual(len(tool_names), 5)
        self.assertIn("get-deployment-history", tool_names)
        self.assertIn("get-platform-status", tool_names)
        self.assertIn("query-platform-context", tool_names)
        self.assertIn("run-governed-command", tool_names)

    def test_observe_call_emits_audit_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            process = self.run_registry_with_pyyaml(
                "--call",
                "get-platform-status",
                "--args-json",
                "{}",
                env={"LV3_AGENT_TOOL_AUDIT_LOG_PATH": str(audit_path)},
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            payload = json.loads(process.stdout)
            self.assertEqual(payload["result"]["tool"], "get-platform-status")
            self.assertFalse(payload["result"]["isError"])
            events = self.read_audit_events(audit_path)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["tool"], "get-platform-status")
            self.assertEqual(events[0]["outcome"], "success")

    def test_report_call_emits_audit_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            process = self.run_registry(
                "--call",
                "export-mcp-tools",
                "--args-json",
                "{}",
                env={"LV3_AGENT_TOOL_AUDIT_LOG_PATH": str(audit_path)},
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            payload = json.loads(process.stdout)
            self.assertEqual(payload["result"]["tool"], "export-mcp-tools")
            self.assertFalse(payload["result"]["isError"])
            self.assertGreaterEqual(payload["result"]["structuredContent"]["count"], 5)
            events = self.read_audit_events(audit_path)
            self.assertEqual(events[0]["tool"], "export-mcp-tools")
            self.assertEqual(events[0]["category"], "report")

    def test_deployment_history_call_returns_filtered_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            process = self.run_registry_with_pyyaml(
                "--call",
                "get-deployment-history",
                "--args-json",
                json.dumps({"service_id": "grafana", "days": 30}),
                env={"LV3_AGENT_TOOL_AUDIT_LOG_PATH": str(audit_path)},
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            payload = json.loads(process.stdout)
            result = payload["result"]["structuredContent"]
            self.assertGreaterEqual(result["count"], 1)
            self.assertTrue(all("grafana" in entry["service_ids"] for entry in result["entries"]))
            events = self.read_audit_events(audit_path)
            self.assertEqual(events[0]["tool"], "get-deployment-history")

    def test_approve_call_emits_audit_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            process = self.run_registry(
                "--call",
                "check-command-approval",
                "--args-json",
                json.dumps(
                    {
                        "command_id": "configure-network",
                        "requester_class": "human_operator",
                        "approver_classes": ["human_operator"],
                        "preflight_passed": True,
                        "validation_passed": True,
                        "receipt_planned": True,
                    }
                ),
                env={"LV3_AGENT_TOOL_AUDIT_LOG_PATH": str(audit_path)},
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            payload = json.loads(process.stdout)
            self.assertTrue(payload["result"]["structuredContent"]["approved"])
            events = self.read_audit_events(audit_path)
            self.assertEqual(events[0]["tool"], "check-command-approval")
            self.assertEqual(events[0]["outcome"], "success")

    def test_execute_call_rejects_without_required_approvals_and_audits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            process = self.run_registry(
                "--call",
                "run-governed-command",
                "--args-json",
                json.dumps(
                    {
                        "command_id": "configure-network",
                        "requester_class": "agent",
                        "approver_classes": [],
                        "preflight_passed": False,
                        "validation_passed": False,
                        "receipt_planned": False,
                        "dry_run": True,
                    }
                ),
                env={"LV3_AGENT_TOOL_AUDIT_LOG_PATH": str(audit_path)},
            )
            self.assertNotEqual(process.returncode, 0)
            payload = json.loads(process.stdout)
            self.assertTrue(payload["result"]["isError"])
            self.assertFalse(payload["result"]["structuredContent"]["approved"])
            events = self.read_audit_events(audit_path)
            self.assertEqual(events[0]["tool"], "run-governed-command")
            self.assertEqual(events[0]["outcome"], "rejected")


if __name__ == "__main__":
    unittest.main()
