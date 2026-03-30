import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "flagsmith_seed.py"
SPEC = importlib.util.spec_from_file_location("flagsmith_seed", SCRIPT_PATH)
flagsmith_seed = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(flagsmith_seed)


def test_list_environments_scopes_requests_to_a_project(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_http_json(base_url, method, path, **kwargs):
        captured["base_url"] = base_url
        captured["method"] = method
        captured["path"] = path
        captured["kwargs"] = kwargs
        return [{"id": 2, "name": "production"}]

    monkeypatch.setattr(flagsmith_seed, "http_json", fake_http_json)

    environments = flagsmith_seed.list_environments("http://flagsmith.internal", "token", 17)

    assert environments == [{"id": 2, "name": "production"}]
    assert captured == {
        "base_url": "http://flagsmith.internal",
        "method": "GET",
        "path": "/api/v1/environments/",
        "kwargs": {"token": "token", "query": {"project": 17}},
    }


def test_ensure_environment_filters_existing_items_by_the_project_id(monkeypatch) -> None:
    requested_project_ids: list[int] = []

    def fake_list_environments(base_url: str, token: str, project_id: int):
        requested_project_ids.append(project_id)
        return [
            {"id": 3, "name": "production", "project": 12, "allow_client_traits": True},
            {"id": 4, "name": "production", "project": 17, "allow_client_traits": True},
        ]

    monkeypatch.setattr(flagsmith_seed, "list_environments", fake_list_environments)

    environment, changed = flagsmith_seed.ensure_environment(
        "http://flagsmith.internal",
        "token",
        17,
        {"name": "production", "allow_client_traits": True},
    )

    assert requested_project_ids == [17]
    assert changed is False
    assert environment["id"] == 4


def test_normalize_feature_state_value_unwraps_typed_flagsmith_payloads() -> None:
    assert flagsmith_seed.normalize_feature_state_value({"type": "unicode", "string_value": "gpt-5.4-mini"}) == (
        "gpt-5.4-mini"
    )
    assert flagsmith_seed.normalize_feature_state_value({"boolean_value": True}) is True
    assert flagsmith_seed.normalize_feature_state_value({"integer_value": 7}) == 7
    assert flagsmith_seed.normalize_feature_state_value("plain-value") == "plain-value"


def test_ensure_feature_state_refetches_after_patch_when_patch_response_is_sparse(monkeypatch) -> None:
    http_calls: list[dict[str, object]] = []
    refreshed_feature_state = {
        "id": 9,
        "enabled": True,
        "feature_state_value": {"type": "unicode", "string_value": "gpt-5.4-mini"},
    }

    monkeypatch.setattr(
        flagsmith_seed,
        "get_feature_state",
        lambda *_args, **_kwargs: {
            "id": 9,
            "enabled": False,
            "feature_state_value": {"type": "unicode", "string_value": "old-model"},
        },
    )

    def fake_http_json(base_url, method, path, **kwargs):
        http_calls.append(
            {
                "base_url": base_url,
                "method": method,
                "path": path,
                "kwargs": kwargs,
            }
        )
        return {"enabled": True, "feature": 2}

    refreshed_calls = {"count": 0}

    def fake_get_feature_state(base_url: str, token: str, environment_id: int, feature_id: int):
        refreshed_calls["count"] += 1
        if refreshed_calls["count"] == 1:
            return {
                "id": 9,
                "enabled": False,
                "feature_state_value": {"type": "unicode", "string_value": "old-model"},
            }
        assert environment_id == 3
        assert feature_id == 2
        return refreshed_feature_state

    monkeypatch.setattr(flagsmith_seed, "get_feature_state", fake_get_feature_state)
    monkeypatch.setattr(flagsmith_seed, "http_json", fake_http_json)

    feature_state, changed = flagsmith_seed.ensure_feature_state(
        "http://flagsmith.internal",
        "token",
        {"id": 3, "api_key": "env-key", "name": "production"},
        {"id": 2, "default_enabled": True, "name": "CONF_LLM_MODEL_NAME"},
        {"enabled": True, "feature_state_value": "gpt-5.4-mini"},
    )

    assert changed is True
    assert feature_state == refreshed_feature_state
    assert refreshed_calls["count"] == 2
    assert http_calls == [
        {
            "base_url": "http://flagsmith.internal",
            "method": "PATCH",
            "path": "/api/v1/environments/env-key/featurestates/9/",
            "kwargs": {
                "token": "token",
                "body": {"enabled": True, "feature_state_value": "gpt-5.4-mini"},
                "expected_status": {200},
            },
        }
    ]


def test_http_json_forces_connection_close_on_each_request(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def getcode(self) -> int:
            return 200

        def read(self) -> bytes:
            return b'{"ok": true}'

    def fake_urlopen(req, timeout=30):
        captured["timeout"] = timeout
        captured["headers"] = {key.lower(): value for key, value in req.header_items()}
        captured["full_url"] = req.full_url
        return FakeResponse()

    monkeypatch.setattr(flagsmith_seed.request, "urlopen", fake_urlopen)

    payload = flagsmith_seed.http_json(
        "http://flagsmith.internal",
        "GET",
        "/api/v1/projects/",
        token="token-123",
        environment_key="env-456",
        query={"project": 17},
    )

    assert payload == {"ok": True}
    assert captured["timeout"] == 30
    assert captured["full_url"] == "http://flagsmith.internal/api/v1/projects/?project=17"
    assert captured["headers"] == {
        "accept": "application/json",
        "authorization": "Token token-123",
        "connection": "close",
        "x-environment-key": "env-456",
    }


def test_sdk_get_flags_wraps_single_object_payloads(monkeypatch) -> None:
    monkeypatch.setattr(
        flagsmith_seed,
        "http_json",
        lambda *_args, **_kwargs: {
            "id": 1,
            "feature": {"name": "SERVERCLAW_EXPERIMENTAL_TOOLS"},
            "enabled": False,
        },
    )

    flags = flagsmith_seed.sdk_get_flags("http://flagsmith.internal", "server-key", "SERVERCLAW_EXPERIMENTAL_TOOLS")

    assert flags == [
        {
            "id": 1,
            "feature": {"name": "SERVERCLAW_EXPERIMENTAL_TOOLS"},
            "enabled": False,
        }
    ]
