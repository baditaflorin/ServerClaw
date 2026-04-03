"""
tests/test_proxmox_tool.py — Unit tests for scripts/proxmox_tool.py

Mock strategy: monkeypatch ProxmoxClient.guest_exec to return preset
(exit_code, stdout, stderr) tuples in call order.  No real Proxmox API is
exercised; the tests are self-contained and run without network access.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import scripts.proxmox_tool as tool


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_PROD_AUTH = {
    "api_url": "https://proxmox.lv3.org:8006/api2/json",
    "full_token_id": "lv3-automation@pve!primary",
    "value": "test-secret",
    "authorization_header": "PVEAPIToken=lv3-automation@pve!primary=test-secret",
}

def _auth_file(tmp_path: Path, extra: dict | None = None) -> Path:
    """Write a valid auth file and return its path."""
    data = dict(_PROD_AUTH)
    if extra:
        data.update(extra)
    p = tmp_path / "auth.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class FakeGuestExec:
    """
    Replaces ProxmoxClient.guest_exec with a call-queue.

    Pre-load responses as a list of (exit_code, stdout, stderr) tuples.
    Each call to guest_exec pops the first response.  Calls are recorded in
    self.calls as {"vmid": int, "command": list[str]}.
    """

    def __init__(self, responses: list[tuple[int, str, str]]) -> None:
        self._responses: list[tuple[int, str, str]] = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        vmid: int,
        command: list[str],
        timeout: int = 60,
    ) -> tuple[int, str, str]:
        self.calls.append({"vmid": vmid, "command": list(command)})
        if not self._responses:
            return (0, "", "")
        return self._responses.pop(0)


# ---------------------------------------------------------------------------
# load_auth
# ---------------------------------------------------------------------------


def test_load_auth_valid(tmp_path: Path) -> None:
    """load_auth returns the full dict when the file is valid."""
    f = _auth_file(tmp_path)
    data = tool.load_auth(str(f))
    assert data["api_url"] == _PROD_AUTH["api_url"]
    assert data["authorization_header"] == _PROD_AUTH["authorization_header"]


def test_load_auth_missing_file(tmp_path: Path) -> None:
    """load_auth exits 1 (via toolkit) when the file does not exist."""
    with pytest.raises(SystemExit) as exc_info:
        tool.load_auth(str(tmp_path / "nonexistent.json"))
    assert exc_info.value.code == 1


def test_load_auth_missing_keys(tmp_path: Path) -> None:
    """load_auth exits 1 (via toolkit) when required keys are absent."""
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"api_url": "https://example.com"}), encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        tool.load_auth(str(bad))
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# ProxmoxClient.guest_exec (mocked at _request level)
# ---------------------------------------------------------------------------


def test_proxmox_client_guest_exec_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """guest_exec polls exec-status until exited=1 and returns (exitcode, stdout, stderr)."""
    requests: list[tuple[str, str]] = []

    def fake_request(
        self: tool.ProxmoxClient, method: str, path: str, payload: dict | None = None
    ) -> Any:
        requests.append((method, path))
        if method == "POST":
            return {"pid": 42}
        # First GET: not done yet; second GET: done
        if len(requests) == 2:
            return {"exited": 0}
        return {"exited": 1, "exitcode": 0, "out-data": "hello\n", "err-data": ""}

    monkeypatch.setattr(tool.ProxmoxClient, "_request", fake_request)
    client = tool.ProxmoxClient(
        api_url="https://proxmox.lv3.org:8006/api2/json",
        authorization_header="PVEAPIToken=x=y",
        node="pve",
    )
    rc, stdout, stderr = client.guest_exec(170, ["echo", "hello"], timeout=5)
    assert rc == 0
    assert stdout == "hello\n"
    assert stderr == ""
    assert requests[0] == ("POST", "/nodes/pve/qemu/170/agent/exec")


def test_proxmox_client_guest_exec_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """guest_exec raises TimeoutError when the command does not finish in time."""

    def fake_request(
        self: tool.ProxmoxClient, method: str, path: str, payload: dict | None = None
    ) -> Any:
        if method == "POST":
            return {"pid": 99}
        return {"exited": 0}  # never finishes

    monkeypatch.setattr(tool.ProxmoxClient, "_request", fake_request)
    monkeypatch.setattr(tool.time, "sleep", lambda _: None)

    _times = iter([0.0, 0.1, 999.0])
    monkeypatch.setattr(tool.time, "monotonic", lambda: next(_times))

    client = tool.ProxmoxClient(
        api_url="https://proxmox.lv3.org:8006/api2/json",
        authorization_header="PVEAPIToken=x=y",
        node="pve",
    )
    with pytest.raises(TimeoutError, match="pid=99"):
        client.guest_exec(170, ["sleep", "100"], timeout=1)


# ---------------------------------------------------------------------------
# guest-exec command
# ---------------------------------------------------------------------------


def test_command_guest_exec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """guest-exec outputs JSON with vmid, exit_code, stdout, stderr."""
    fake = FakeGuestExec([(0, "nginx-lv3\n", "")])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file(tmp_path)),
        "guest-exec", "--vmid", "110", "--",
        "hostname",
    ])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["vmid"] == 110
    assert out["exit_code"] == 0
    assert "nginx-lv3" in out["stdout"]


def test_command_guest_exec_shell_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """--shell wraps the command in bash -c."""
    fake = FakeGuestExec([(0, "ok", "")])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    tool.main([
        "--auth-file", str(_auth_file(tmp_path)),
        "guest-exec", "--vmid", "170", "--shell",
        "echo", "hello",
    ])
    assert fake.calls[0]["command"] == ["bash", "-c", "echo hello"]


def test_command_guest_exec_propagate_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """--propagate-exit-code forwards the guest exit code as the tool exit code."""
    fake = FakeGuestExec([(3, "", "error")])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file(tmp_path)),
        "guest-exec", "--vmid", "170", "--propagate-exit-code", "--",
        "false",
    ])
    assert rc == 3


# ---------------------------------------------------------------------------
# docker-ps command
# ---------------------------------------------------------------------------


def test_command_docker_ps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """docker-ps returns a JSON array of container objects."""
    container_json = json.dumps({"Names": "coolify", "Status": "Up 5 minutes"})
    fake = FakeGuestExec([(0, container_json + "\n", "")])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file(tmp_path)),
        "docker-ps", "--vmid", "170",
    ])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["vmid"] == 170
    assert len(out["containers"]) == 1
    assert out["containers"][0]["Names"] == "coolify"


# ---------------------------------------------------------------------------
# install-key command
# ---------------------------------------------------------------------------


def test_command_install_key_new_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """install-key appends the key and exits 0 when the key is not already present."""
    pubkey = "ssh-ed25519 AAAAC3Nza some-comment"
    fake = FakeGuestExec([
        (0, "ssh-rsa AAAA existing-key\n", ""),   # read existing
        (0, "", ""),                                # append + chmod
    ])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file(tmp_path)),
        "install-key", "--vmid", "171", "--pubkey", pubkey,
    ])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "installed"
    assert out["key_fingerprint"] == "some-comment"
    # Second call should be the bash append script
    assert fake.calls[1]["command"][0] == "bash"


def test_command_install_key_already_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """install-key exits 2 (no-op) when the key is already in authorized_keys."""
    pubkey = "ssh-ed25519 AAAAC3Nza some-comment"
    fake = FakeGuestExec([(0, pubkey + "\n", "")])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file(tmp_path)),
        "install-key", "--vmid", "171", "--pubkey", pubkey,
    ])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["status"] == "already_present"
    assert len(fake.calls) == 1  # no append call made


# ---------------------------------------------------------------------------
# Topology resolution
# ---------------------------------------------------------------------------


def test_resolve_topology_cli_overrides_auth_file(
    tmp_path: Path,
) -> None:
    """Explicit CLI --coolify-vmid overrides the topology embedded in the auth file."""
    import argparse

    auth = dict(_PROD_AUTH)
    auth["topology"] = {"coolify_vmid": 170, "node": "pve"}
    args = argparse.Namespace(
        topology_file=None,
        env="prod",
        node=None,
        coolify_vmid=999,   # CLI override
        container=None,
        coolify_container=None,
        db_user=None,
    )
    topo = tool._resolve_topology(args, auth)
    assert topo["coolify_vmid"] == 999


def test_resolve_topology_defaults_without_topology(tmp_path: Path) -> None:
    """_resolve_topology returns sensible defaults when no topology is configured."""
    import argparse

    args = argparse.Namespace(
        topology_file=None,
        env="prod",
        node=None,
        coolify_vmid=None,
        container=None,
        coolify_container=None,
        db_user=None,
    )
    topo = tool._resolve_topology(args, dict(_PROD_AUTH))
    assert topo["node"] == "pve"
    assert topo["coolify_db_container"] == "coolify-db"
    assert topo["coolify_db_user"] == "coolify"
    assert topo["coolify_container"] == "coolify"
