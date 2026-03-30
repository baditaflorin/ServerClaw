from __future__ import annotations

import json
import socket

from platform.ansible import woodpecker


class FakeGiteaClient:
    def __init__(self, applications):
        self.applications = list(applications)
        self.created: list[dict] = []
        self.updated: list[tuple[int, dict]] = []
        self.deleted: list[int] = []

    def list_oauth_applications(self):
        return list(self.applications)

    def create_oauth_application(self, payload):
        created = dict(payload, id=9, client_id="woodpecker-client", client_secret="woodpecker-secret")
        self.created.append(created)
        return created

    def update_oauth_application(self, application_id, payload):
        self.updated.append((application_id, payload))
        return payload

    def delete_oauth_application(self, application_id):
        self.deleted.append(application_id)


def test_api_candidates_try_both_current_and_legacy_prefixes() -> None:
    assert woodpecker._api_candidates("/user") == ["/user", "/api/user"]
    assert woodpecker._api_candidates("/api/user/token") == ["/user/token", "/api/user/token"]


def test_split_repository_full_name_rejects_invalid_values() -> None:
    try:
        woodpecker.split_repository_full_name("ops")
    except ValueError as exc:
        assert "owner/name" in str(exc)
    else:
        raise AssertionError("Expected split_repository_full_name to reject single-segment names")


def test_ensure_gitea_oauth_application_reuses_existing_credentials_when_present() -> None:
    client = FakeGiteaClient(
        [
            {
                "id": 4,
                "name": "LV3 Woodpecker",
                "redirect_uris": ["https://ci.lv3.org/authorize"],
                "confidential_client": True,
                "skip_secondary_authorization": True,
                "client_id": "existing-client",
            }
        ]
    )

    result = woodpecker.ensure_gitea_oauth_application(
        client,
        name="LV3 Woodpecker",
        redirect_uri="https://ci.lv3.org/authorize",
        existing_client_id="existing-client",
        existing_client_secret="existing-secret",
    )

    assert result == {
        "id": 4,
        "client_id": "existing-client",
        "client_secret": "existing-secret",
        "recreated": False,
    }
    assert client.updated == []
    assert client.deleted == []
    assert client.created == []


def test_ensure_gitea_oauth_application_recreates_when_secret_is_missing() -> None:
    client = FakeGiteaClient(
        [
            {
                "id": 4,
                "name": "LV3 Woodpecker",
                "redirect_uris": ["https://old.example/authorize"],
                "confidential_client": True,
                "skip_secondary_authorization": False,
            }
        ]
    )

    result = woodpecker.ensure_gitea_oauth_application(
        client,
        name="LV3 Woodpecker",
        redirect_uri="https://ci.lv3.org/authorize",
    )

    assert result["client_id"] == "woodpecker-client"
    assert result["client_secret"] == "woodpecker-secret"
    assert result["recreated"] is True
    assert client.updated == [
        (
            4,
            {
                "name": "LV3 Woodpecker",
                "redirect_uris": ["https://ci.lv3.org/authorize"],
                "confidential_client": True,
                "skip_secondary_authorization": True,
            },
        )
    ]
    assert client.deleted == [4]
    assert len(client.created) == 1


def test_request_candidates_fall_back_from_404_to_legacy_api_path() -> None:
    client = woodpecker.WoodpeckerClient("http://example.test", "token", verify_ssl=False)
    seen: list[str] = []

    def fake_request_once(path, *, method="GET", payload=None, expected_statuses=None, accept_json=True):
        seen.append(path)
        if path == "/user":
            raise woodpecker._HttpStatusError("GET /user returned HTTP 404", status=404, body="")
        return 200, {"login": "ops-gitea"}

    client._request_once = fake_request_once  # type: ignore[method-assign]

    assert client.get_user() == {"login": "ops-gitea"}
    assert seen == ["/user", "/api/user"]


def test_api_client_get_user_falls_back_from_html_shell_to_api_json() -> None:
    client = woodpecker.WoodpeckerClient("http://example.test", "token", verify_ssl=False)
    seen: list[str] = []

    def fake_request_once(path, *, method="GET", payload=None, expected_statuses=None, accept_json=True):
        seen.append(path)
        if path == "/user":
            raise json.JSONDecodeError("Expecting value", "<!DOCTYPE html>", 0)
        return 200, {"login": "ops-gitea"}

    client._request_once = fake_request_once  # type: ignore[method-assign]

    assert client.get_user() == {"login": "ops-gitea"}
    assert seen == ["/user", "/api/user"]


def test_list_repository_secrets_returns_empty_list_when_api_body_is_empty() -> None:
    client = woodpecker.WoodpeckerClient("http://example.test", "token", verify_ssl=False)
    seen: list[str] = []

    def fake_request_once(path, *, method="GET", payload=None, expected_statuses=None, accept_json=True):
        seen.append(path)
        if path == "/repos/1/secrets":
            raise json.JSONDecodeError("Expecting value", "<!DOCTYPE html>", 0)
        return 200, None

    client._request_once = fake_request_once  # type: ignore[method-assign]

    assert client.list_repository_secrets(1) == []
    assert seen == ["/repos/1/secrets", "/api/repos/1/secrets"]


def test_trigger_pipeline_accepts_no_content_response() -> None:
    client = woodpecker.WoodpeckerClient("http://example.test", "token", verify_ssl=False)
    seen: list[tuple[str, str, set[int] | None]] = []

    def fake_request_candidates(paths, *, method="GET", payload=None, expected_statuses=None, accept_json=True):
        seen.append((paths[0], method, expected_statuses))
        return 204, None

    client._request_candidates = fake_request_candidates  # type: ignore[method-assign]

    assert client.trigger_pipeline(1, branch="main") is None
    assert seen == [("/repos/1/pipelines", "POST", {200, 204})]


def test_rewrite_url_if_host_unresolvable_uses_fallback_base_url(monkeypatch) -> None:
    def fake_getaddrinfo(hostname, *args, **kwargs):
        if hostname == "git.lv3.org":
            raise socket.gaierror("not found")
        return [("family", "socktype", "proto", "canonname", ("127.0.0.1", 0))]

    monkeypatch.setattr(woodpecker.socket, "getaddrinfo", fake_getaddrinfo)

    assert woodpecker._rewrite_url_if_host_unresolvable(
        "http://git.lv3.org:3009/user/login?redirect_to=%2F",
        "http://100.64.0.1:3009",
    ) == "http://100.64.0.1:3009/user/login?redirect_to=%2F"


def test_rewrite_url_if_host_unresolvable_leaves_resolvable_host_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(
        woodpecker.socket,
        "getaddrinfo",
        lambda hostname, *args, **kwargs: [("family", "socktype", "proto", "canonname", ("127.0.0.1", 0))],
    )

    assert woodpecker._rewrite_url_if_host_unresolvable(
        "https://ci.lv3.org/authorize",
        "http://100.64.0.1:3009",
    ) == "https://ci.lv3.org/authorize"


def test_pick_oauth_grant_form_prefers_the_positive_submit_button() -> None:
    html = """
    <form action="/login/oauth/grant" method="post">
      <input type="hidden" name="_csrf" value="csrf-token">
      <input type="hidden" name="client_id" value="client-id">
      <input type="hidden" name="state" value="state-token">
      <input type="hidden" name="redirect_uri" value="https://ci.lv3.org/authorize">
      <button type="submit" name="granted" value="false">Cancel</button>
      <button type="submit" name="granted" value="true">Authorize Application</button>
    </form>
    """

    action_url, payload = woodpecker._pick_oauth_grant_form(
        html,
        "http://100.64.0.1:3009/login/oauth/authorize?client_id=client-id",
    ) or ("", {})

    assert action_url == "http://100.64.0.1:3009/login/oauth/grant"
    assert payload == {
        "_csrf": "csrf-token",
        "client_id": "client-id",
        "state": "state-token",
        "redirect_uri": "https://ci.lv3.org/authorize",
        "granted": "true",
    }


def test_parse_woodpecker_csrf_token_reads_web_config_assignment() -> None:
    assert (
        woodpecker._parse_woodpecker_csrf_token(
            '\nwindow.WOODPECKER_CSRF = "csrf-token";\nwindow.WOODPECKER_VERSION = "3.13.0";\n'
        )
        == "csrf-token"
    )


def test_session_login_via_gitea_submits_oauth_grant_after_sign_in(monkeypatch) -> None:
    client = woodpecker.WoodpeckerSessionClient(
        "https://ci.lv3.org",
        verify_ssl=False,
        redirect_fallback_base_url="http://100.64.0.1:3009",
    )
    calls: list[tuple[str, dict]] = []
    login_html = """
    <form action="/user/login" method="post">
      <input type="hidden" name="_csrf" value="login-csrf">
      <input type="text" name="user_name" value="">
      <input type="password" name="password" value="">
    </form>
    """
    grant_html = """
    <form action="/login/oauth/grant" method="post">
      <input type="hidden" name="_csrf" value="grant-csrf">
      <input type="hidden" name="client_id" value="client-id">
      <input type="hidden" name="state" value="state-token">
      <input type="hidden" name="redirect_uri" value="https://ci.lv3.org/authorize">
      <button type="submit" name="granted" value="true">Authorize</button>
      <button type="submit" name="granted" value="false">Cancel</button>
    </form>
    """

    def fake_request(url_or_path, **kwargs):
        calls.append((url_or_path, kwargs))
        if url_or_path == "/authorize":
            return 200, login_html, {}, "http://100.64.0.1:3009/user/login"
        if url_or_path == "http://100.64.0.1:3009/user/login":
            assert kwargs["method"] == "POST"
            assert kwargs["form"]["_csrf"] == "login-csrf"
            assert kwargs["form"]["user_name"] == "ops-gitea"
            assert kwargs["form"]["password"] == "secret-password"
            return (
                200,
                grant_html,
                {},
                "http://100.64.0.1:3009/login/oauth/authorize?client_id=client-id",
            )
        if url_or_path == "http://100.64.0.1:3009/login/oauth/grant":
            assert kwargs["method"] == "POST"
            assert kwargs["form"]["_csrf"] == "grant-csrf"
            assert kwargs["form"]["client_id"] == "client-id"
            assert kwargs["form"]["redirect_uri"] == "https://ci.lv3.org/authorize"
            assert kwargs["form"]["granted"] == "true"
            return 200, "<!DOCTYPE html><html><body>Woodpecker</body></html>", {}, "https://ci.lv3.org/authorize"
        raise AssertionError(f"Unexpected request: {url_or_path!r}")

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "get_user", lambda: {"login": "ops-gitea"})

    assert client.login_via_gitea("ops-gitea", "secret-password") == {"login": "ops-gitea"}
    assert [item[0] for item in calls] == [
        "/authorize",
        "http://100.64.0.1:3009/user/login",
        "http://100.64.0.1:3009/login/oauth/grant",
    ]


def test_session_get_user_falls_back_from_html_shell_to_api_json(monkeypatch) -> None:
    client = woodpecker.WoodpeckerSessionClient("https://ci.lv3.org", verify_ssl=False)
    seen: list[str] = []

    def fake_request(path, **kwargs):
        seen.append(path)
        if path == "/user":
            raise json.JSONDecodeError("Expecting value", "<!DOCTYPE html>", 0)
        return 200, {"login": "ops-gitea"}, {}, "https://ci.lv3.org/api/user"

    monkeypatch.setattr(client, "_request", fake_request)

    assert client.get_user() == {"login": "ops-gitea"}
    assert seen == ["/user", "/api/user"]


def test_session_create_user_token_falls_back_from_html_shell(monkeypatch) -> None:
    client = woodpecker.WoodpeckerSessionClient("https://ci.lv3.org", verify_ssl=False)
    seen: list[str] = []

    def fake_request(path, **kwargs):
        seen.append(path)
        if path == "/web-config.js":
            return 200, 'window.WOODPECKER_CSRF = "csrf-token";', {}, "https://ci.lv3.org/web-config.js"
        if path == "/user/token":
            assert kwargs["headers"]["X-CSRF-TOKEN"] == "csrf-token"
            return 200, "<!DOCTYPE html><html><body>Shell</body></html>", {}, "https://ci.lv3.org/user/token"
        assert kwargs["headers"]["X-CSRF-TOKEN"] == "csrf-token"
        return 200, '"token-123"', {}, "https://ci.lv3.org/api/user/token"

    monkeypatch.setattr(client, "_request", fake_request)

    assert client.create_user_token() == "token-123"
    assert seen == ["/web-config.js", "/user/token", "/api/user/token"]
