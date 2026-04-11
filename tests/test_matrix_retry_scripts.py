from __future__ import annotations

from pathlib import Path

import matrix_admin_register
import matrix_bridge_smoke


def test_matrix_admin_login_retries_rate_limit_then_succeeds(monkeypatch, tmp_path: Path) -> None:
    responses = [
        (429, {"errcode": "M_LIMIT_EXCEEDED", "retry_after_ms": 1000}),
        (200, {"access_token": "token-123", "user_id": "@ops:example.com"}),
    ]
    sleeps: list[float] = []

    monkeypatch.setattr(
        matrix_admin_register,
        "request_json",
        lambda *args, **kwargs: responses.pop(0),
    )
    monkeypatch.setattr(matrix_admin_register.time, "sleep", lambda seconds: sleeps.append(seconds))

    token_file = tmp_path / "matrix-access-token.txt"
    ok, payload = matrix_admin_register.login(
        "https://matrix.example.com",
        "ops",
        "secret",
        access_token_file=token_file,
    )

    assert ok is True
    assert payload["access_token"] == "token-123"
    assert sleeps == [1.0]
    assert token_file.read_text(encoding="utf-8").strip() == "token-123"


def test_matrix_admin_login_returns_rate_limit_payload_when_budget_expires(monkeypatch) -> None:
    monkeypatch.setattr(
        matrix_admin_register,
        "request_json",
        lambda *args, **kwargs: (429, {"errcode": "M_LIMIT_EXCEEDED", "retry_after_ms": 5000}),
    )
    monkeypatch.setattr(matrix_admin_register.time, "sleep", lambda seconds: None)

    ok, payload = matrix_admin_register.login(
        "https://matrix.example.com",
        "ops",
        "secret",
        max_rate_limit_wait_seconds=1,
    )

    assert ok is False
    assert payload["errcode"] == "M_LIMIT_EXCEEDED"


def test_matrix_bridge_login_retries_rate_limit_then_succeeds(monkeypatch, tmp_path: Path) -> None:
    responses = [
        (429, {"errcode": "M_LIMIT_EXCEEDED", "retry_after_ms": 1000}),
        (200, {"access_token": "bridge-token", "user_id": "@ops:example.com"}),
    ]
    sleeps: list[float] = []

    monkeypatch.setattr(
        matrix_bridge_smoke,
        "request_json",
        lambda *args, **kwargs: responses.pop(0),
    )
    monkeypatch.setattr(matrix_bridge_smoke.time, "sleep", lambda seconds: sleeps.append(seconds))

    token_file = tmp_path / "matrix-bridge-token.txt"
    payload = matrix_bridge_smoke.login(
        "https://matrix.example.com",
        "ops",
        "secret",
        access_token_file=token_file,
    )

    assert payload["access_token"] == "bridge-token"
    assert sleeps == [1.0]
    assert token_file.read_text(encoding="utf-8").strip() == "bridge-token"
