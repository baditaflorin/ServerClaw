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

_PROD_TOPO = {
    "node": "pve",
    "coolify_vmid": 170,
    "coolify_apps_vmid": 171,
    "coolify_db_container": "coolify-db",
    "coolify_db_user": "coolify",
    "coolify_container": "coolify",
}


def _auth_file(tmp_path: Path, extra: dict | None = None) -> Path:
    """Write a valid auth file and return its path."""
    data = dict(_PROD_AUTH)
    if extra:
        data.update(extra)
    p = tmp_path / "auth.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _auth_file_with_topology(tmp_path: Path) -> Path:
    """Write a valid auth file with embedded topology."""
    data = dict(_PROD_AUTH)
    data["topology"] = dict(_PROD_TOPO)
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
    """load_auth raises FileNotFoundError when the file does not exist."""
    with pytest.raises(FileNotFoundError, match="not found"):
        tool.load_auth(str(tmp_path / "nonexistent.json"))


def test_load_auth_missing_keys(tmp_path: Path) -> None:
    """load_auth raises ValueError when required keys are absent."""
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"api_url": "https://example.com"}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required keys"):
        tool.load_auth(str(bad))


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
# coolify-db-exec command
# ---------------------------------------------------------------------------


def test_command_coolify_db_exec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """coolify-db-exec runs psql and returns the result JSON."""
    fake = FakeGuestExec([(0, "UPDATE 2\n", "")])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file_with_topology(tmp_path)),
        "coolify-db-exec",
        "--sql", "UPDATE applications SET destination_id=34 WHERE destination_id=1",
    ])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["exit_code"] == 0
    assert "UPDATE 2" in out["stdout"]
    assert out["container"] == "coolify-db"


def test_command_coolify_db_exec_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """coolify-db-exec exits 1 when psql returns non-zero."""
    fake = FakeGuestExec([(1, "", "ERROR: relation does not exist\n")])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file_with_topology(tmp_path)),
        "coolify-db-exec",
        "--sql", "SELECT * FROM nonexistent_table",
    ])
    assert rc == 1


# ---------------------------------------------------------------------------
# coolify-clear-cache command
# ---------------------------------------------------------------------------


def test_command_coolify_clear_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """coolify-clear-cache runs artisan commands and exits 0."""
    fake = FakeGuestExec([(0, "Application cache cleared!\nConfiguration cache cleared!\n", "")])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file_with_topology(tmp_path)),
        "coolify-clear-cache",
    ])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["container"] == "coolify"
    assert "cache:clear" in fake.calls[0]["command"][-1]


# ---------------------------------------------------------------------------
# coolify-migrate-apps command
# ---------------------------------------------------------------------------


def test_command_coolify_migrate_apps_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """coolify-migrate-apps finds destination IDs, updates the DB, and clears cache."""
    fake = FakeGuestExec([
        (0, "1", ""),                           # from_id lookup
        (0, "34", ""),                          # to_id lookup
        (0, "2", ""),                           # count
        (0, "repo-smoke\neducation-wemeshup", ""),  # app names
        (0, "UPDATE 2", ""),                    # migration UPDATE
        (0, "Application cache cleared!", ""),  # cache clear
    ])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file_with_topology(tmp_path)),
        "coolify-migrate-apps",
        "--from", "coolify-lv3",
        "--to", "coolify-apps-lv3",
    ])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "migrated"
    assert out["from_destination_id"] == 1
    assert out["to_destination_id"] == 34
    assert out["migrated_count"] == 2
    assert "repo-smoke" in out["migrated_apps"]
    assert "education-wemeshup" in out["migrated_apps"]
    assert len(fake.calls) == 6


def test_command_coolify_migrate_apps_nothing_to_migrate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """coolify-migrate-apps exits 2 (no-op) when count == 0."""
    fake = FakeGuestExec([
        (0, "1", ""),   # from_id
        (0, "34", ""),  # to_id
        (0, "0", ""),   # count == 0
    ])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file_with_topology(tmp_path)),
        "coolify-migrate-apps",
        "--from", "coolify-lv3",
        "--to", "coolify-apps-lv3",
    ])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["status"] == "nothing_to_migrate"
    assert out["migrated_count"] == 0
    assert len(fake.calls) == 3  # no UPDATE or cache clear


def test_command_coolify_migrate_apps_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """--dry-run reports what would be migrated without running UPDATE or cache clear."""
    fake = FakeGuestExec([
        (0, "1", ""),
        (0, "34", ""),
        (0, "1", ""),
        (0, "repo-smoke", ""),
    ])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file_with_topology(tmp_path)),
        "coolify-migrate-apps",
        "--from", "coolify-lv3",
        "--to", "coolify-apps-lv3",
        "--dry-run",
    ])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "dry_run"
    assert out["migrated_count"] == 1
    assert len(fake.calls) == 4  # no UPDATE or cache clear after dry-run


def test_command_coolify_migrate_apps_missing_server(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """coolify-migrate-apps exits 1 when the source server is not found in the DB."""
    fake = FakeGuestExec([
        (0, "", ""),    # from_id not found (empty result)
        (0, "34", ""),  # to_id found
    ])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file_with_topology(tmp_path)),
        "coolify-migrate-apps",
        "--from", "nonexistent-server",
        "--to", "coolify-apps-lv3",
    ])
    assert rc == 1
    err = capsys.readouterr().err
    assert "nonexistent-server" in err


def test_command_coolify_migrate_apps_unsafe_server_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """coolify-migrate-apps exits 1 on server names with SQL-unsafe characters."""
    fake = FakeGuestExec([])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file_with_topology(tmp_path)),
        "coolify-migrate-apps",
        "--from", "server'; DROP TABLE applications; --",
        "--to", "coolify-apps-lv3",
    ])
    assert rc == 1
    assert len(fake.calls) == 0  # no DB calls made


def test_command_coolify_migrate_apps_uses_topology_vmid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """coolify-migrate-apps reads coolify_vmid from the topology embedded in the auth file."""
    fake = FakeGuestExec([
        (0, "1", ""),
        (0, "34", ""),
        (0, "1", ""),
        (0, "repo-smoke", ""),
        (0, "UPDATE 1", ""),
        (0, "cache cleared", ""),
    ])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file_with_topology(tmp_path)),
        "coolify-migrate-apps",
        "--from", "coolify-lv3",
        "--to", "coolify-apps-lv3",
    ])
    assert rc == 0
    # All guest_exec calls should target VMID 170 (from topology)
    for call in fake.calls:
        assert call["vmid"] == 170


# ---------------------------------------------------------------------------
# coolify-install-deploy-key command
# ---------------------------------------------------------------------------


def test_command_coolify_install_deploy_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """coolify-install-deploy-key installs the key on the target VM."""
    pubkey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC0gB481 coolify-deploy"
    fake = FakeGuestExec([
        (0, "", ""),    # no existing keys
        (0, "", ""),    # append
    ])
    monkeypatch.setattr(tool.ProxmoxClient, "guest_exec", fake)

    rc = tool.main([
        "--auth-file", str(_auth_file(tmp_path)),
        "coolify-install-deploy-key",
        "--vmid", "171",
        "--pubkey", pubkey,
    ])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "installed"
    assert out["key_fingerprint"] == "coolify-deploy"


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


# ---------------------------------------------------------------------------
# _safe_identifier
# ---------------------------------------------------------------------------


def test_safe_identifier_valid() -> None:
    assert tool._safe_identifier("coolify-lv3", "--from") == "coolify-lv3"
    assert tool._safe_identifier("coolify_apps_lv3", "--to") == "coolify_apps_lv3"


def test_safe_identifier_rejects_sql_injection() -> None:
    with pytest.raises(ValueError, match="Unsafe value"):
        tool._safe_identifier("'; DROP TABLE applications; --", "--from")


def test_safe_identifier_rejects_spaces() -> None:
    with pytest.raises(ValueError, match="Unsafe value"):
        tool._safe_identifier("server name", "--from")
