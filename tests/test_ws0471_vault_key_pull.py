"""Tests for ADR 0469 — connection.yml vault key pull."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "deployment.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("deployment_for_ws0471", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["deployment_for_ws0471"] = module
    spec.loader.exec_module(module)
    return module


def _make_stub_vault_cli(tmp_path: Path, payload: str, exit_code: int = 0) -> Path:
    """Write a tiny shell script that mimics `openbao read -field=X path`.

    Writes payload to a sidecar file and the stub `cat`s it — avoids
    quoting hell with heredocs and shell escaping.
    """
    stub = tmp_path / "fake-openbao.sh"
    body_path = tmp_path / "fake-openbao.body"
    body_path.write_text(payload)
    if exit_code == 0:
        stub.write_text(f"#!/bin/sh\ncat {body_path}\nexit 0\n")
    else:
        stub.write_text(f"#!/bin/sh\necho 'fake error' >&2\nexit {exit_code}\n")
    stub.chmod(0o755)
    return stub


def test_resolve_ssh_key_spec_string_path(tmp_path):
    mod = _load_module()
    p = mod._resolve_ssh_key_spec("bootstrap.id_ed25519", tmp_path)
    assert str(p).endswith(".local/ssh/bootstrap.id_ed25519")


def test_resolve_ssh_key_spec_absolute_path(tmp_path):
    mod = _load_module()
    p = mod._resolve_ssh_key_spec("/etc/ssh/ssh_host_key", tmp_path)
    assert str(p) == "/etc/ssh/ssh_host_key"


def test_materialize_vault_key_writes_tempfile(tmp_path, monkeypatch):
    mod = _load_module()
    stub = _make_stub_vault_cli(tmp_path, "test-key-content\n")
    monkeypatch.setenv("LV3_VAULT_FETCH_CMD", str(stub))
    monkeypatch.setenv("LV3_VAULT_KEY_TMPDIR", str(tmp_path))
    p = mod._materialize_vault_key({"vault": "secret/path/to/key"}, tmp_path)
    assert p.is_file()
    assert p.read_text() == "test-key-content\n"
    # Mode must be 0600.
    mode = p.stat().st_mode & 0o777
    assert mode == 0o600


def test_materialize_vault_key_uses_field(tmp_path, monkeypatch):
    """Stub captures argv to confirm --field is forwarded."""
    mod = _load_module()
    capture = tmp_path / "argv.txt"
    stub = tmp_path / "capture.sh"
    stub.write_text(f'#!/bin/sh\necho "$@" > {capture}\nprintf "key-data"\n')
    stub.chmod(0o755)
    monkeypatch.setenv("LV3_VAULT_FETCH_CMD", str(stub))
    monkeypatch.setenv("LV3_VAULT_KEY_TMPDIR", str(tmp_path))
    mod._materialize_vault_key({"vault": "secret/foo", "field": "ssh_key"}, tmp_path)
    assert capture.is_file()
    argv = capture.read_text()
    assert "secret/foo" in argv
    assert "ssh_key" in argv


def test_materialize_vault_key_raises_on_fetch_failure(tmp_path, monkeypatch):
    mod = _load_module()
    stub = _make_stub_vault_cli(tmp_path, "", exit_code=2)
    monkeypatch.setenv("LV3_VAULT_FETCH_CMD", str(stub))
    monkeypatch.setenv("LV3_VAULT_KEY_TMPDIR", str(tmp_path))
    with pytest.raises(mod.DeploymentError):
        mod._materialize_vault_key({"vault": "secret/foo"}, tmp_path)


def test_materialize_vault_key_raises_on_empty_body(tmp_path, monkeypatch):
    mod = _load_module()
    stub = _make_stub_vault_cli(tmp_path, "")
    monkeypatch.setenv("LV3_VAULT_FETCH_CMD", str(stub))
    monkeypatch.setenv("LV3_VAULT_KEY_TMPDIR", str(tmp_path))
    with pytest.raises(mod.DeploymentError):
        mod._materialize_vault_key({"vault": "secret/foo"}, tmp_path)


def test_materialize_vault_key_rejects_missing_vault_field(tmp_path):
    mod = _load_module()
    with pytest.raises(mod.DeploymentError):
        mod._materialize_vault_key({"field": "x"}, tmp_path)


def test_materialize_vault_key_rejects_empty_vault_path(tmp_path):
    mod = _load_module()
    with pytest.raises(mod.DeploymentError):
        mod._materialize_vault_key({"vault": ""}, tmp_path)


# --- schema acceptance ----------------------------------------------------


def test_connection_schema_accepts_string_key_form():
    pytest.importorskip("jsonschema")
    import json

    from jsonschema import Draft202012Validator

    schema = json.loads((REPO_ROOT / "config" / "contracts" / "deployment-v1" / "connection.schema.json").read_text())
    payload = {
        "schema_version": 1,
        "proxmox_host": {"addr": "1.2.3.4", "port": 22, "user": "ops", "key": "bootstrap.id_ed25519"},
        "guest_ssh": {"user": "ops", "key": "bootstrap.id_ed25519"},
    }
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert not errors


def test_connection_schema_accepts_vault_key_form():
    pytest.importorskip("jsonschema")
    import json

    from jsonschema import Draft202012Validator

    schema = json.loads((REPO_ROOT / "config" / "contracts" / "deployment-v1" / "connection.schema.json").read_text())
    payload = {
        "schema_version": 1,
        "proxmox_host": {"addr": "1.2.3.4", "port": 22, "user": "ops", "key": {"vault": "secret/host-key"}},
        "guest_ssh": {"user": "ops", "key": {"vault": "secret/guest-key", "field": "private_key"}},
    }
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert not errors, [e.message for e in errors]


def test_connection_schema_rejects_other_dict_shapes():
    pytest.importorskip("jsonschema")
    import json

    from jsonschema import Draft202012Validator

    schema = json.loads((REPO_ROOT / "config" / "contracts" / "deployment-v1" / "connection.schema.json").read_text())
    payload = {
        "schema_version": 1,
        "proxmox_host": {"addr": "1.2.3.4", "port": 22, "user": "ops", "key": {"unknown": "x"}},
        "guest_ssh": {"user": "ops", "key": "bootstrap.id_ed25519"},
    }
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert errors  # extra property under key.dict form
