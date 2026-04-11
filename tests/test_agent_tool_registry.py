import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
        self.assertGreaterEqual(len(tool_names), 6)
        self.assertIn("browser-run-session", tool_names)
        self.assertIn("get-deployment-history", tool_names)
        self.assertIn("get-platform-status", tool_names)
        self.assertIn("get-maintenance-windows", tool_names)
        self.assertIn("list-serverclaw-skills", tool_names)
        self.assertIn("query-platform-context", tool_names)
        self.assertIn("run-governed-command", tool_names)

    def test_browser_run_session_uses_base_url_override_and_audits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            captured: dict[str, object] = {}

            class Handler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:  # noqa: N802
                    content_length = int(self.headers.get("Content-Length", "0"))
                    body = self.rfile.read(content_length).decode("utf-8")
                    captured["path"] = self.path
                    captured["headers"] = dict(self.headers.items())
                    captured["body"] = json.loads(body)

                    payload = {
                        "run_id": "run-123",
                        "requested_url": "https://example.com",
                        "final_url": "https://example.com/final",
                        "title": "Browser Runner Smoke",
                        "navigation_status": "completed",
                        "text_excerpt": "done",
                        "selector_results": [{"name": "heading", "text": "Browser Runner Smoke"}],
                        "artifacts": [{"kind": "screenshot", "path": "artifacts/run-123/final-page.png"}],
                        "action_log": [{"index": 0, "action": "goto", "detail": "loaded https://example.com"}],
                        "warnings": [],
                    }
                    encoded = json.dumps(payload).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)

                def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                    return None

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                process = self.run_registry_with_pyyaml(
                    "--call",
                    "browser-run-session",
                    "--args-json",
                    json.dumps(
                        {
                            "url": "https://example.com",
                            "steps": [{"action": "goto", "url": "https://example.com/final"}],
                            "capture_screenshot": True,
                            "timeout_seconds": 12,
                        }
                    ),
                    env={
                        "LV3_AGENT_TOOL_AUDIT_LOG_PATH": str(audit_path),
                        "LV3_BROWSER_RUNNER_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                    },
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(process.returncode, 0, process.stderr)
            payload = json.loads(process.stdout)
            self.assertEqual(payload["result"]["tool"], "browser-run-session")
            self.assertFalse(payload["result"]["isError"])
            structured = payload["result"]["structuredContent"]
            self.assertEqual(structured["run_id"], "run-123")
            self.assertEqual(captured["path"], "/sessions")
            self.assertEqual(captured["body"]["url"], "https://example.com")
            self.assertEqual(captured["body"]["timeout_seconds"], 12)
            events = self.read_audit_events(audit_path)
            self.assertEqual(events[0]["tool"], "browser-run-session")
            self.assertEqual(events[0]["outcome"], "success")

    def test_get_maintenance_windows_uses_local_state_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            state_path = Path(temp_dir) / "maintenance-windows.json"
            state_path.write_text(
                json.dumps(
                    {
                        "maintenance/grafana": {
                            "window_id": "44444444-4444-4444-4444-444444444444",
                            "service_id": "grafana",
                            "reason": "deploy",
                            "opened_by": {"class": "operator", "id": "ops-linux"},
                            "opened_at": "2026-03-23T09:50:00Z",
                            "expected_duration_minutes": 30,
                            "auto_close_at": "2099-03-23T10:20:00Z",
                            "correlation_id": "deploy:grafana",
                        }
                    }
                )
            )
            process = self.run_registry_with_pyyaml(
                "--call",
                "get-maintenance-windows",
                "--args-json",
                "{}",
                env={
                    "LV3_AGENT_TOOL_AUDIT_LOG_PATH": str(audit_path),
                    "LV3_MAINTENANCE_WINDOWS_FILE": str(state_path),
                },
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            payload = json.loads(process.stdout)
            self.assertEqual(payload["result"]["tool"], "get-maintenance-windows")
            self.assertEqual(payload["result"]["structuredContent"]["count"], 1)
            self.assertEqual(payload["result"]["structuredContent"]["windows"][0]["service_id"], "grafana")

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

    def test_serverclaw_skills_call_returns_workspace_resolution_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            process = self.run_registry_with_pyyaml(
                "--call",
                "list-serverclaw-skills",
                "--args-json",
                json.dumps({"workspace_id": "ops", "include_prompt_manifest": True}),
                env={"LV3_AGENT_TOOL_AUDIT_LOG_PATH": str(audit_path)},
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            payload = json.loads(process.stdout)
            result = payload["result"]["structuredContent"]
            self.assertEqual(result["workspace_id"], "ops")
            active = {entry["skill_id"]: entry for entry in result["active_skills"]}
            self.assertEqual(active["platform-observe"]["source_tier"], "workspace")
            self.assertTrue(any(entry["skill_id"] == "platform-observe" for entry in result["prompt_manifest"]))
            events = self.read_audit_events(audit_path)
            self.assertEqual(events[0]["tool"], "list-serverclaw-skills")
            self.assertEqual(events[0]["outcome"], "success")

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

    def test_execute_call_dry_run_returns_bounded_runtime_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            process = self.run_registry(
                "--call",
                "run-governed-command",
                "--args-json",
                json.dumps(
                    {
                        "command_id": "network-impairment-matrix",
                        "requester_class": "human_operator",
                        "approver_classes": ["human_operator"],
                        "preflight_passed": True,
                        "validation_passed": True,
                        "receipt_planned": True,
                        "parameters": {"NETWORK_IMPAIRMENT_MATRIX_ARGS": "target_class=staging --approve-risk"},
                        "dry_run": True,
                    }
                ),
                env={"LV3_AGENT_TOOL_AUDIT_LOG_PATH": str(audit_path)},
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            payload = json.loads(process.stdout)
            structured = payload["result"]["structuredContent"]
            self.assertEqual(structured["command_id"], "network-impairment-matrix")
            self.assertTrue(structured["approved"])
            self.assertFalse(structured["executed"])
            self.assertEqual(structured["runtime_host"], "docker-runtime-lv3")
            self.assertTrue(structured["unit_name"].startswith("lv3-governed-network-impairment-matrix-"))
            self.assertEqual(
                structured["parameters"],
                {"NETWORK_IMPAIRMENT_MATRIX_ARGS": "target_class=staging --approve-risk"},
            )
            self.assertTrue(structured["stdout_log"].endswith(".stdout.log"))
            self.assertTrue(structured["receipt_path"].endswith(".json"))
            events = self.read_audit_events(audit_path)
            self.assertEqual(events[0]["tool"], "run-governed-command")
            self.assertEqual(events[0]["outcome"], "success")


if __name__ == "__main__":
    unittest.main()
