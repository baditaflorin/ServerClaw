from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from urllib.error import HTTPError

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import outline_client  # noqa: E402
from outline_client import OutlineClient, OutlineError  # noqa: E402


class Response:
    def __enter__(self) -> Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"ok":true}'


class SequencedOpener:
    def __init__(self, statuses: list[int]) -> None:
        self.statuses = list(statuses)
        self.calls = 0

    def open(self, _request: object, timeout: int) -> Response:
        assert timeout == 60
        self.calls += 1
        if self.statuses:
            status = self.statuses.pop(0)
            raise HTTPError(
                "https://wiki.example/api/test",
                status,
                "request failed",
                {},
                io.BytesIO(b"rate limited" if status == 429 else b"denied"),
            )
        return Response()


def test_outline_client_retries_only_rate_limits_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    opener = SequencedOpener([429, 429])
    delays: list[float] = []
    monkeypatch.setattr(outline_client.time, "sleep", delays.append)

    response = OutlineClient("https://wiki.example", opener=opener).call("documents.info", {"id": "doc"})

    assert response == {"ok": True}
    assert opener.calls == 3
    assert delays == [30, 60]


def test_outline_client_reports_exhausted_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    opener = SequencedOpener([429, 429, 429, 429])
    delays: list[float] = []
    monkeypatch.setattr(outline_client.time, "sleep", delays.append)

    with pytest.raises(OutlineError, match="HTTP 429: rate limited"):
        OutlineClient("https://wiki.example", opener=opener).call("documents.info", {"id": "doc"})

    assert opener.calls == 4
    assert delays == [30, 60, 90]


def test_outline_client_does_not_retry_non_rate_limit_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    opener = SequencedOpener([403])
    delays: list[float] = []
    monkeypatch.setattr(outline_client.time, "sleep", delays.append)

    with pytest.raises(OutlineError, match="HTTP 403: denied"):
        OutlineClient("https://wiki.example", opener=opener).call("documents.info", {"id": "doc"})

    assert opener.calls == 1
    assert delays == []
