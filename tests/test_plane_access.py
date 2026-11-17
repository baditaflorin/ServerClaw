from __future__ import annotations

import io
import json
import os
import socket
import stat
import urllib.error
from pathlib import Path

import pytest

from platform.ansible.plane import PlaneClient, PlaneError
from platform.ansible.plane_access import plane_local_dir, plane_transport


def unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def is_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def test_private_transport_starts_and_cleans_up_its_own_loopback_listener(tmp_path, monkeypatch):
    port = unused_port()
    auth = tmp_path / "admin-auth.json"
    auth.write_text(json.dumps({"base_url": f"http://127.0.0.1:{port}"}))
    (tmp_path / "transport.json").write_text(json.dumps({"ssh_target": "example-vm", "remote_port": 8093}))
    ssh = tmp_path / "ssh"
    ssh.write_text("""#!/usr/bin/env python3
import socket, sys
spec = sys.argv[sys.argv.index('-L') + 1].split(':')
assert spec[0] == spec[2] == '127.0.0.1'
s = socket.socket(); s.bind((spec[0], int(spec[1]))); s.listen()
sys.stdin.read()
""")
    ssh.chmod(ssh.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    assert not is_listening(port)
    with plane_transport(auth):
        assert is_listening(port)
    assert not is_listening(port)


def test_worktree_uses_main_credentials_when_its_partial_overlay_lacks_auth(tmp_path, monkeypatch):
    from types import SimpleNamespace

    worktree = tmp_path / "worktree"
    main = tmp_path / "main"
    (worktree / ".local" / "plane").mkdir(parents=True)
    shared = main / ".local" / "plane"
    shared.mkdir(parents=True)
    (shared / "admin-auth.json").write_text("{}")
    monkeypatch.setattr(
        "platform.ansible.plane_access.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=f"worktree {main}\nHEAD 1234\n"),
    )
    assert plane_local_dir(worktree) == shared


@pytest.mark.parametrize("url", ["http://0.0.0.0:1234", "https://127.0.0.1:1234", "http://localhost:1234"])
def test_transport_rejects_noncanonical_local_listener(tmp_path, url):
    auth = tmp_path / "admin-auth.json"
    auth.write_text(json.dumps({"base_url": url}))
    (tmp_path / "transport.json").write_text(json.dumps({"ssh_target": "example-vm", "remote_port": 8093}))
    with pytest.raises(ValueError, match="127.0.0.1"):
        with plane_transport(auth):
            pass


def test_verify_api_key_distinguishes_unauthorized_from_disconnected(monkeypatch):
    client = PlaneClient("http://127.0.0.1:1", "example", max_rate_limit_retries=0)

    def unauthorized(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", None, io.BytesIO(b"{}"))

    monkeypatch.setattr(client._opener, "open", unauthorized)
    assert client.verify_api_key() is False

    def disconnected(request, timeout):
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    monkeypatch.setattr(client._opener, "open", disconnected)
    with pytest.raises(PlaneError, match="connection failed"):
        client.verify_api_key()
