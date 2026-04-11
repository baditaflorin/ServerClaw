from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from types import SimpleNamespace

from platform.ansible.woodpecker import WoodpeckerError
from scripts import woodpecker_tool


class FakeWoodpeckerClient:
    def __init__(self) -> None:
        self.pipeline_lists = [
            [],
            [{"number": 7, "status": "pending"}],
        ]
        self.wait_calls: list[tuple[int, int, int, int]] = []

    def lookup_repository(self, full_name: str):
        assert full_name == "ops/proxmox-host_server"
        return {"id": 1, "full_name": full_name}

    def list_pipelines(self, repo_id: int, *, branch: str | None = None):
        assert repo_id == 1
        assert branch == "branch-under-test"
        if len(self.pipeline_lists) > 1:
            return self.pipeline_lists.pop(0)
        return self.pipeline_lists[0]

    def trigger_pipeline(self, repo_id: int, *, branch: str, variables: dict[str, str] | None = None):
        assert repo_id == 1
        assert branch == "branch-under-test"
        assert variables == {"KEY": "VALUE"}
        return None

    def wait_for_pipeline(
        self,
        repo_id: int,
        number: int,
        *,
        timeout_seconds: int = 600,
        poll_seconds: int = 5,
    ):
        self.wait_calls.append((repo_id, number, timeout_seconds, poll_seconds))
        return {"number": number, "status": "success"}


def test_command_trigger_pipeline_waits_for_discovered_run_when_trigger_returns_no_content(monkeypatch) -> None:
    client = FakeWoodpeckerClient()
    monkeypatch.setattr(
        woodpecker_tool,
        "build_client",
        lambda auth_file: (client, {"repo_full_name": "ops/proxmox-host_server"}),
    )
    monkeypatch.setattr(woodpecker_tool.time, "sleep", lambda _: None)
    buffer = io.StringIO()

    args = SimpleNamespace(
        auth_file="ignored.json",
        repo="ops/proxmox-host_server",
        branch="branch-under-test",
        variable=["KEY=VALUE"],
        wait=True,
        timeout=30,
        poll_interval=0,
    )

    with redirect_stdout(buffer):
        exit_code = woodpecker_tool.command_trigger_pipeline(args)

    assert exit_code == 0
    assert client.wait_calls == [(1, 7, 30, 0)]
    assert json.loads(buffer.getvalue()) == {"number": 7, "status": "success"}


def test_discover_triggered_pipeline_raises_when_no_run_appears(monkeypatch) -> None:
    client = FakeWoodpeckerClient()
    client.pipeline_lists = [[]]
    monkeypatch.setattr(woodpecker_tool.time, "sleep", lambda _: None)
    clock = iter([0.0, 0.0, 1.0, 2.1])
    monkeypatch.setattr(woodpecker_tool.time, "monotonic", lambda: next(clock))

    try:
        woodpecker_tool._discover_triggered_pipeline(
            client,
            1,
            branch="branch-under-test",
            timeout_seconds=2,
            poll_seconds=0,
            baseline=[],
        )
    except WoodpeckerError as exc:
        assert "no pipeline run became visible" in str(exc)
    else:
        raise AssertionError("Expected pipeline discovery to fail when no new run appears")
