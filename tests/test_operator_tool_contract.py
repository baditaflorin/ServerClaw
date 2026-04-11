"""
tests/test_operator_tool_contract.py

Contract compliance tests for ADR 0343 — Operator Tool Interface Contract.
All tests use only stdlib + pytest (no extra dependencies).
"""

from __future__ import annotations

import json
import sys
import tempfile
import os
from pathlib import Path

import pytest

# Ensure scripts/ is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import controller_automation_toolkit as cat


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(tmp_path: Path, data: dict, filename: str = "auth.json") -> Path:
    p = tmp_path / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# load_proxmox_auth
# ---------------------------------------------------------------------------


class TestLoadProxmoxAuth:
    def test_good_file(self, tmp_path):
        data = {"api_url": "https://pve:8006", "authorization_header": "PVEAPIToken=root@pam!tok=abc"}
        p = _write_json(tmp_path, data)
        result = cat.load_proxmox_auth(str(p))
        assert result["api_url"] == "https://pve:8006"
        assert result["authorization_header"].startswith("PVEAPIToken=")

    def test_missing_file_exits_1(self, tmp_path):
        with pytest.raises(SystemExit) as exc_info:
            cat.load_proxmox_auth(str(tmp_path / "nonexistent.json"))
        assert exc_info.value.code == 1

    def test_missing_keys_exits_1(self, tmp_path):
        # Only one of the two required keys
        p = _write_json(tmp_path, {"api_url": "https://pve:8006"})
        with pytest.raises(SystemExit) as exc_info:
            cat.load_proxmox_auth(str(p))
        assert exc_info.value.code == 1

    def test_invalid_json_exits_1(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not-json", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            cat.load_proxmox_auth(str(bad))
        assert exc_info.value.code == 1

    def test_missing_file_writes_to_stderr(self, tmp_path, capsys):
        with pytest.raises(SystemExit):
            cat.load_proxmox_auth(str(tmp_path / "ghost.json"))
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
        assert "ghost.json" in captured.err


# ---------------------------------------------------------------------------
# tool_output
# ---------------------------------------------------------------------------


class TestToolOutput:
    def test_writes_json_with_status(self, capsys):
        cat.tool_output("changed", key="value", count=3)
        captured = capsys.readouterr()
        obj = json.loads(captured.out)
        assert obj["status"] == "changed"
        assert obj["key"] == "value"
        assert obj["count"] == 3

    def test_minimal_status_only(self, capsys):
        cat.tool_output("no_op")
        captured = capsys.readouterr()
        obj = json.loads(captured.out)
        assert obj == {"status": "no_op"}

    def test_output_is_valid_json(self, capsys):
        cat.tool_output("installed", detail="ssh key added", vmid=171)
        captured = capsys.readouterr()
        # Must not raise
        parsed = json.loads(captured.out)
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# tool_exit_noop
# ---------------------------------------------------------------------------


class TestToolExitNoop:
    def test_exits_with_code_2(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            cat.tool_exit_noop(reason="already_installed")
        assert exc_info.value.code == 2

    def test_writes_no_op_status_to_stdout(self, capsys):
        with pytest.raises(SystemExit):
            cat.tool_exit_noop(reason="already_installed")
        captured = capsys.readouterr()
        obj = json.loads(captured.out)
        assert obj["status"] == "no_op"
        assert obj["reason"] == "already_installed"

    def test_no_op_with_no_extra_fields(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            cat.tool_exit_noop()
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        obj = json.loads(captured.out)
        assert obj["status"] == "no_op"


# ---------------------------------------------------------------------------
# tool_exit_error
# ---------------------------------------------------------------------------


class TestToolExitError:
    def test_exits_with_code_1(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            cat.tool_exit_error("something went wrong")
        assert exc_info.value.code == 1

    def test_writes_to_stderr(self, capsys):
        with pytest.raises(SystemExit):
            cat.tool_exit_error("auth file missing")
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
        assert "auth file missing" in captured.err

    def test_with_extra_fields_writes_json_to_stdout(self, capsys):
        with pytest.raises(SystemExit):
            cat.tool_exit_error("bad config", code="auth_file_not_found")
        captured = capsys.readouterr()
        obj = json.loads(captured.out)
        assert obj["status"] == "error"
        assert obj["code"] == "auth_file_not_found"
        assert "bad config" in obj["detail"]

    def test_without_extra_fields_no_stdout(self, capsys):
        with pytest.raises(SystemExit):
            cat.tool_exit_error("silent error")
        captured = capsys.readouterr()
        # No JSON on stdout when no extra fields are given
        assert captured.out.strip() == ""


# ---------------------------------------------------------------------------
# load_topology_snapshot
# ---------------------------------------------------------------------------


class TestLoadTopologySnapshot:
    def _make_snapshot(self, tmp_path: Path) -> Path:
        data = {
            "environments": {
                "prod": {"nodes": ["pve1", "pve2"], "vms": {"171": "coolify-apps"}},
                "staging": {"nodes": ["pve-staging"], "vms": {}},
            }
        }
        p = tmp_path / "topology-snapshot.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def test_valid_snapshot_returns_env_dict(self, tmp_path):
        snap = self._make_snapshot(tmp_path)
        result = cat.load_topology_snapshot(str(snap), "prod")
        assert result["nodes"] == ["pve1", "pve2"]
        assert "171" in result["vms"]

    def test_missing_file_returns_empty_dict(self, tmp_path):
        result = cat.load_topology_snapshot(str(tmp_path / "missing.json"), "prod")
        assert result == {}

    def test_missing_env_returns_empty_dict(self, tmp_path, capsys):
        snap = self._make_snapshot(tmp_path)
        result = cat.load_topology_snapshot(str(snap), "dev")
        assert result == {}
        captured = capsys.readouterr()
        assert "dev" in captured.err

    def test_invalid_json_returns_empty_dict(self, tmp_path, capsys):
        bad = tmp_path / "bad-snap.json"
        bad.write_text("{not valid json", encoding="utf-8")
        result = cat.load_topology_snapshot(str(bad), "prod")
        assert result == {}
        captured = capsys.readouterr()
        assert "WARNING" in captured.err

    def test_staging_env(self, tmp_path):
        snap = self._make_snapshot(tmp_path)
        result = cat.load_topology_snapshot(str(snap), "staging")
        assert result["nodes"] == ["pve-staging"]


# ---------------------------------------------------------------------------
# proxmox_guest_exec
# ---------------------------------------------------------------------------


class TestProxmoxGuestExec:
    class _FakeClient:
        """Minimal fake ProxmoxClient for testing proxmox_guest_exec."""

        def __init__(self):
            self.calls = []

        def guest_exec(self, vmid: int, command: list, timeout: int = 60):
            self.calls.append({"vmid": vmid, "command": command, "timeout": timeout})
            return (0, "hello\n", "")

    def test_delegates_to_client_guest_exec(self):
        client = self._FakeClient()
        exit_code, stdout, stderr = cat.proxmox_guest_exec(client, 171, ["echo", "hello"])
        assert exit_code == 0
        assert stdout == "hello\n"
        assert len(client.calls) == 1
        assert client.calls[0]["vmid"] == 171
        assert client.calls[0]["command"] == ["echo", "hello"]

    def test_coerces_vmid_to_int(self):
        client = self._FakeClient()
        cat.proxmox_guest_exec(client, "171", ["id"])  # type: ignore[arg-type]
        assert isinstance(client.calls[0]["vmid"], int)
        assert client.calls[0]["vmid"] == 171

    def test_coerces_command_to_list(self):
        client = self._FakeClient()
        # Pass a tuple to ensure it is converted to list
        cat.proxmox_guest_exec(client, 100, ("ls", "-la"))  # type: ignore[arg-type]
        assert isinstance(client.calls[0]["command"], list)

    def test_custom_timeout_passed(self):
        client = self._FakeClient()
        cat.proxmox_guest_exec(client, 100, ["uptime"], timeout=120)
        assert client.calls[0]["timeout"] == 120


# ---------------------------------------------------------------------------
# woodpecker_tool — ADR 0343 load_auth compliance
# ---------------------------------------------------------------------------


class TestWoodpeckerToolContract:
    """Verify woodpecker_tool uses toolkit load_operator_auth (ADR 0343)."""

    def test_uses_toolkit_auth(self):
        """woodpecker_tool must not define its own load_auth."""
        import woodpecker_tool
        import inspect

        src = inspect.getsource(woodpecker_tool)
        assert "def load_auth" not in src, "woodpecker_tool must not define its own load_auth"

    def test_build_client_fails_on_missing_file(self, tmp_path):
        """build_client must exit 1 on missing auth file (via load_operator_auth)."""
        import woodpecker_tool

        with pytest.raises(SystemExit) as exc:
            woodpecker_tool.build_client(str(tmp_path / "nonexistent.json"))
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# portainer_tool — ADR 0343 load_auth compliance
# ---------------------------------------------------------------------------


class TestPortainerToolContract:
    """Verify portainer_tool uses toolkit load_operator_auth (ADR 0343)."""

    def test_uses_toolkit_auth(self):
        """portainer_tool must not define its own load_auth."""
        import portainer_tool
        import inspect

        src = inspect.getsource(portainer_tool)
        assert "def load_auth" not in src, "portainer_tool must not define its own load_auth"

    def test_command_whoami_fails_on_missing_file(self, tmp_path):
        """command_whoami must exit 1 on missing auth file (via load_operator_auth)."""
        import portainer_tool
        import argparse

        args = argparse.Namespace(auth_file=str(tmp_path / "nonexistent.json"))
        with pytest.raises(SystemExit) as exc:
            portainer_tool.command_whoami(args)
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# plane_tool — ADR 0343 load_auth compliance
# ---------------------------------------------------------------------------


class TestPlaneToolContract:
    """Verify plane_tool uses toolkit load_operator_auth (ADR 0343)."""

    def test_uses_toolkit_auth(self):
        """plane_tool must not define its own load_auth."""
        import plane_tool
        import inspect

        src = inspect.getsource(plane_tool)
        assert "def load_auth" not in src, "plane_tool must not define its own load_auth"

    def test_build_client_fails_on_missing_file(self, tmp_path):
        """build_client must exit 1 on missing auth file (via load_operator_auth)."""
        import plane_tool

        with pytest.raises(SystemExit) as exc:
            plane_tool.build_client(str(tmp_path / "nonexistent.json"))
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# semaphore_tool — ADR 0343 load_auth compliance
# ---------------------------------------------------------------------------


class TestSemaphoreToolContract:
    """Verify semaphore_tool uses toolkit load_operator_auth (ADR 0343)."""

    def test_uses_toolkit_auth(self):
        """semaphore_tool must not define its own load_auth."""
        import semaphore_tool
        import inspect

        src = inspect.getsource(semaphore_tool)
        assert "def load_auth" not in src, "semaphore_tool must not define its own load_auth"

    def test_build_client_fails_on_missing_file(self, tmp_path):
        """build_client must exit 1 on missing auth file (via load_operator_auth)."""
        import semaphore_tool

        with pytest.raises(SystemExit) as exc:
            semaphore_tool.build_client(str(tmp_path / "nonexistent.json"))
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# uptime_kuma_tool — ADR 0343 load_auth compliance
# ---------------------------------------------------------------------------

socketio_available = True
try:
    import socketio as _socketio  # noqa: F401
except ImportError:
    socketio_available = False


@pytest.mark.skipif(not socketio_available, reason="socketio not installed")
class TestUptimeKumaToolContract:
    """Verify uptime_kuma_tool uses toolkit load_operator_auth (ADR 0343)."""

    def test_uses_toolkit_auth(self):
        """uptime_kuma_tool must not define its own load_auth_json."""
        import uptime_kuma_tool
        import inspect

        src = inspect.getsource(uptime_kuma_tool)
        assert "def load_auth_json" not in src, "uptime_kuma_tool must not define its own load_auth_json"

    def test_resolve_auth_fails_on_missing_file(self, tmp_path):
        """resolve_auth must exit 1 on missing auth file (via load_operator_auth)."""
        import uptime_kuma_tool
        import argparse

        args = argparse.Namespace(
            auth_file=str(tmp_path / "nonexistent.json"),
            base_url=None,
        )
        with pytest.raises(SystemExit) as exc:
            uptime_kuma_tool.resolve_auth(args)
        assert exc.value.code == 1
