from __future__ import annotations

import importlib.util
import os
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "config" / "windmill" / "scripts" / "deploy-and-promote.py"
SPEC = importlib.util.spec_from_file_location("deploy_and_promote_module", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_windmill_wrapper_forwards_platform_trace_id(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    workflow = repo_root / "scripts" / "promotion_pipeline.py"
    workflow.parent.mkdir()
    workflow.write_text("print('ok')\n")
    captured: dict[str, object] = {}

    class Result:
        returncode = 0
        stdout = '{"status":"ok"}'
        stderr = ""

    def fake_run(command, cwd, text, capture_output, check, env):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        return Result()

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    monkeypatch.setenv("PLATFORM_TRACE_ID", "trace-windmill-123")

    payload = MODULE.main(
        service="api_gateway", staging_receipt="receipts/live-applies/staging/test.json", repo_path=str(repo_root)
    )

    assert payload["status"] == "ok"
    assert payload["trace_id"] == "trace-windmill-123"
    assert captured["env"]["PLATFORM_TRACE_ID"] == "trace-windmill-123"
