from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "authentik-account-expiry-reaper.py"


def load_reaper():
    spec = importlib.util.spec_from_file_location("authentik_account_expiry_reaper", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reaper_blocks_without_authentik_runtime_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    reaper = load_reaper()
    monkeypatch.setenv("LV3_AUTHENTIK_URL", "")
    monkeypatch.setenv("LV3_AUTHENTIK_BOOTSTRAP_TOKEN", "")

    assert reaper.main() == {
        "status": "blocked",
        "reason": "Missing LV3_AUTHENTIK_URL or LV3_AUTHENTIK_BOOTSTRAP_TOKEN.",
    }


def test_reaper_disables_only_active_expired_users_and_follows_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    reaper = load_reaper()
    calls: list[tuple[str, str, dict | None]] = []

    def fake_api(method: str, _base_url: str, path: str, _token: str, body=None):
        calls.append((method, path, body))
        if method == "GET" and "page=1" in path:
            return 200, {
                "results": [
                    {
                        "pk": 10,
                        "username": "expired-active",
                        "is_active": True,
                        "attributes": {"account_expires_at": "2000-01-01T00:00:00Z"},
                    },
                    {
                        "pk": 11,
                        "username": "expired-disabled",
                        "is_active": False,
                        "attributes": {"account_expires_at": "2000-01-01T00:00:00Z"},
                    },
                ],
                "pagination": {"next": 2},
            }
        if method == "GET" and "page=2" in path:
            return 200, {
                "results": [
                    {
                        "pk": 12,
                        "username": "future",
                        "is_active": True,
                        "attributes": {"account_expires_at": "2999-01-01T00:00:00+00:00"},
                    },
                    {
                        "pk": 13,
                        "username": "invalid",
                        "is_active": True,
                        "attributes": {"account_expires_at": "not-a-date"},
                    },
                ],
                "pagination": {"next": None},
            }
        if method == "PATCH" and path == "/core/users/10/":
            assert body == {"is_active": False}
            return 200, {"pk": 10}
        raise AssertionError((method, path, body))

    monkeypatch.setattr(reaper, "_api", fake_api)

    result = reaper.main(authentik_url="https://id.example.com", api_token="test-token")

    assert result["status"] == "ok"
    assert result["disabled"] == [
        {"username": "expired-active", "expires_at": "2000-01-01T00:00:00Z", "action": "disabled"}
    ]
    assert result["skipped_count"] == 2
    assert result["error_count"] == 1
    assert [path for method, path, _ in calls if method == "GET"] == [
        "/core/users/?page=1&page_size=100",
        "/core/users/?page=2&page_size=100",
    ]


def test_reaper_dry_run_accepts_legacy_single_item_list_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    reaper = load_reaper()

    def fake_api(method: str, _base_url: str, path: str, _token: str, body=None):
        assert method == "GET"
        assert body is None
        assert path == "/core/users/?page=1&page_size=100"
        return 200, {
            "results": [
                {
                    "pk": 10,
                    "username": "expired",
                    "is_active": True,
                    "attributes": {"account_expires_at": ["2000-01-01T00:00:00Z"]},
                }
            ],
            "pagination": {"next": None},
        }

    monkeypatch.setattr(reaper, "_api", fake_api)

    result = reaper.main(dry_run=True, authentik_url="https://id.example.com", api_token="test-token")

    assert result["status"] == "ok"
    assert result["disabled"] == [{"username": "expired", "expires_at": "2000-01-01T00:00:00Z", "action": "dry_run"}]


def test_reaper_reports_authentik_list_failure_without_attempting_a_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    reaper = load_reaper()
    monkeypatch.setattr(reaper, "_api", lambda *_args, **_kwargs: (401, None))

    assert reaper.main(authentik_url="https://id.example.com", api_token="test-token") == {
        "status": "error",
        "reason": "Authentik user listing returned HTTP 401.",
    }
