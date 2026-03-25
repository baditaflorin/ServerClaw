from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "resource_lock_tool.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_tool_creates_state_lists_locks_and_releases(tmp_path: Path) -> None:
    state_path = tmp_path / "locks.json"

    ensured = run_tool("--state-path", str(state_path), "ensure-state")
    assert ensured.returncode == 0, ensured.stderr
    ensured_payload = json.loads(ensured.stdout)
    assert ensured_payload["status"] == "ready"
    assert state_path.exists()

    acquired = run_tool(
        "--state-path",
        str(state_path),
        "acquire",
        "--resource",
        "vm:130/service:netbox",
        "--holder",
        "agent:ctx-a",
        "--lock-type",
        "exclusive",
        "--context-id",
        "ctx-a",
        "--metadata-json",
        '{"tool":"test"}',
    )
    assert acquired.returncode == 0, acquired.stderr
    acquired_payload = json.loads(acquired.stdout)
    lock_id = acquired_payload["lock"]["lock_id"]

    listed = run_tool("--state-path", str(state_path), "list")
    assert listed.returncode == 0, listed.stderr
    listed_payload = json.loads(listed.stdout)
    assert listed_payload["count"] == 1
    assert listed_payload["locks"][0]["metadata"] == {"tool": "test"}

    heartbeat = run_tool("--state-path", str(state_path), "heartbeat", "--lock-id", lock_id, "--ttl-seconds", "450")
    assert heartbeat.returncode == 0, heartbeat.stderr
    heartbeat_payload = json.loads(heartbeat.stdout)
    assert heartbeat_payload["status"] == "refreshed"
    assert heartbeat_payload["lock"]["lock_id"] == lock_id

    released = run_tool(
        "--state-path",
        str(state_path),
        "release",
        "--resource",
        "vm:130/service:netbox",
        "--holder",
        "agent:ctx-a",
    )
    assert released.returncode == 0, released.stderr
    assert json.loads(released.stdout)["released"] == 1

    empty = run_tool("--state-path", str(state_path), "list")
    assert empty.returncode == 0, empty.stderr
    assert json.loads(empty.stdout)["count"] == 0


def test_tool_reports_conflict_and_invalid_release_filters(tmp_path: Path) -> None:
    state_path = tmp_path / "locks.json"

    first = run_tool(
        "--state-path",
        str(state_path),
        "acquire",
        "--resource",
        "vm:130",
        "--holder",
        "agent:ctx-a",
        "--lock-type",
        "exclusive",
    )
    assert first.returncode == 0, first.stderr

    conflict = run_tool(
        "--state-path",
        str(state_path),
        "acquire",
        "--resource",
        "vm:130/service:netbox",
        "--holder",
        "agent:ctx-b",
        "--lock-type",
        "shared",
    )
    assert conflict.returncode == 2
    assert "locked" in conflict.stderr

    invalid_release = run_tool("--state-path", str(state_path), "release")
    assert invalid_release.returncode == 2
    assert "requires at least one" in invalid_release.stderr
