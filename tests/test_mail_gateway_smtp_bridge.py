from __future__ import annotations

import importlib.util
import json
import smtplib
import socket
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = REPO_ROOT / "roles" / "mail_platform_runtime" / "files" / "mail-gateway" / "smtp_bridge.py"


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_handle:
        socket_handle.bind(("127.0.0.1", 0))
        return int(socket_handle.getsockname()[1])


def load_bridge(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    pytest.importorskip("aiosmtpd")
    monkeypatch.setenv("BREVO_API_KEY", "test-brevo-key")
    monkeypatch.setenv("DEFAULT_FROM_EMAIL", "server@example.com")
    monkeypatch.setenv("DEFAULT_FROM_NAME", "LV3 Test Bridge")
    monkeypatch.setenv("DEFAULT_REPLY_TO_EMAIL", "server@example.com")
    monkeypatch.setenv("LOCAL_SMTP_USERNAME", "bridge-user")
    monkeypatch.setenv("LOCAL_SMTP_PASSWORD", "bridge-password")
    monkeypatch.setenv("SMTP_BRIDGE_STATE_FILE", str(tmp_path / "bridge-state.json"))
    monkeypatch.setenv("SMTP_BRIDGE_MAX_MESSAGE_BYTES", "65536")

    spec = importlib.util.spec_from_file_location("smtp_bridge_test", BRIDGE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_authenticated_smtp_submission_uses_transactional_provider_without_logging_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bridge = load_bridge(monkeypatch, tmp_path)
    captured: dict[str, object] = {}

    async def fake_submit(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(bridge, "submit_to_provider", fake_submit)
    port = free_tcp_port()
    controller = bridge.Controller(
        bridge.TransactionalSMTPHandler(),
        hostname="127.0.0.1",
        port=port,
        data_size_limit=65536,
        auth_required=True,
        auth_require_tls=False,
        auth_callback=bridge.authenticate,
    )
    controller.start()
    try:
        with smtplib.SMTP("127.0.0.1", port, timeout=10) as client:
            code, _ = client.login("bridge-user", "bridge-password")
            assert code == 235
            client.sendmail(
                "server@example.com",
                ["operator@example.com"],
                b"From: server@example.com\r\n"
                b"To: operator@example.com\r\n"
                b"Subject: Recovery\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n"
                b"\r\n"
                b"Use the private recovery link.\r\n",
            )
    finally:
        controller.stop()

    assert captured == {
        "recipients": ["operator@example.com"],
        "subject": "Recovery",
        "text": "Use the private recovery link.\r\n",
        "html": None,
    }
    state = json.loads((tmp_path / "bridge-state.json").read_text(encoding="utf-8"))
    assert state["accepted_total"] == 1
    assert state["provider_success_total"] == 1
    assert state["provider_failure_total"] == 0


def test_smtp_bridge_rejects_invalid_credentials_and_unauthorized_sender(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bridge = load_bridge(monkeypatch, tmp_path)

    async def fake_submit(**_kwargs) -> None:
        return None

    monkeypatch.setattr(bridge, "submit_to_provider", fake_submit)
    port = free_tcp_port()
    controller = bridge.Controller(
        bridge.TransactionalSMTPHandler(),
        hostname="127.0.0.1",
        port=port,
        data_size_limit=65536,
        auth_required=True,
        auth_require_tls=False,
        auth_callback=bridge.authenticate,
    )
    controller.start()
    try:
        with smtplib.SMTP("127.0.0.1", port, timeout=10) as client, pytest.raises(smtplib.SMTPAuthenticationError):
            client.login("bridge-user", "wrong-password")
        with smtplib.SMTP("127.0.0.1", port, timeout=10) as client:
            client.login("bridge-user", "bridge-password")
            with pytest.raises(smtplib.SMTPDataError) as error:
                client.sendmail(
                    "other@example.com",
                    ["operator@example.com"],
                    b"From: other@example.com\r\nTo: operator@example.com\r\nSubject: Unauthorized\r\n\r\nBody\r\n",
                )
            assert error.value.smtp_code == 550
    finally:
        controller.stop()

    state = json.loads((tmp_path / "bridge-state.json").read_text(encoding="utf-8"))
    assert state["auth_failure_total"] >= 1
    assert state["rejected_total"] == 1
