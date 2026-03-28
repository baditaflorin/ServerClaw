from __future__ import annotations

import json
from pathlib import Path

from platform.ansible import plane
from scripts import sync_adrs_to_plane


def test_parse_query_error_prefers_error_message() -> None:
    location = "https://tasks.lv3.org/god-mode/?error_code=5185&error_message=ADMIN_USER_DOES_NOT_EXIST"

    assert plane._parse_query_error(location) == "ADMIN_USER_DOES_NOT_EXIST"


def test_plane_session_prime_uses_csrf_token_endpoint() -> None:
    client = plane.PlaneSessionClient("http://plane.invalid", verify_ssl=False)

    def fake_request(path: str, **kwargs):
        assert path == "/auth/get-csrf-token/"
        assert kwargs["expected_statuses"] == {200}
        return 200, {"csrf_token": "csrf-token-value"}, {}

    client._request = fake_request  # type: ignore[method-assign]

    client.prime()

    assert client._csrf_headers() == {"X-CSRFToken": "csrf-token-value"}


def test_plane_session_list_workspaces_falls_back_to_instance_admin_route() -> None:
    client = plane.PlaneSessionClient("http://plane.invalid", verify_ssl=False)
    calls: list[str] = []

    def fake_request(path: str, **kwargs):
        calls.append(path)
        if path == "/api/users/me/workspaces/?per_page=1000":
            raise plane.PlaneError("GET /api/users/me/workspaces/?per_page=1000 returned HTTP 401: {}")
        if path == "/api/instances/workspaces/?per_page=10":
            return 200, {"results": [{"slug": "lv3-platform"}]}, {}
        raise AssertionError(path)

    client._request = fake_request  # type: ignore[method-assign]

    assert client.list_workspaces() == [{"slug": "lv3-platform"}]
    assert calls == [
        "/api/users/me/workspaces/?per_page=1000",
        "/api/instances/workspaces/?per_page=10",
    ]


def test_state_name_for_adr_treats_not_implemented_as_todo() -> None:
    record = plane.AdrRecord(
        adr_id="0193",
        title="Plane Kanban Task Board",
        status="Accepted",
        implementation_status="Not Implemented",
        path=Path("docs/adr/0193-plane-kanban-task-board.md"),
        summary="summary",
    )

    assert plane.state_name_for_adr(record) == "Todo"


def test_state_name_for_adr_treats_in_progress_as_in_progress() -> None:
    record = plane.AdrRecord(
        adr_id="0193",
        title="Plane Kanban Task Board",
        status="Accepted",
        implementation_status="In Progress",
        path=Path("docs/adr/0193-plane-kanban-task-board.md"),
        summary="summary",
    )

    assert plane.state_name_for_adr(record) == "In Progress"


def test_render_adr_description_uses_repo_relative_path_once() -> None:
    record = plane.AdrRecord(
        adr_id="0193",
        title="Plane Kanban Task Board",
        status="Accepted",
        implementation_status="Implemented",
        path=Path("docs/adr/0193-plane-kanban-task-board.md"),
        summary="summary",
    )

    rendered = plane.render_adr_description(record)

    assert "docs/adr/0193-plane-kanban-task-board.md" in rendered
    assert "docs/adr/docs/adr/" not in rendered


def test_plane_client_retries_rate_limited_requests(monkeypatch) -> None:
    client = plane.PlaneClient(
        "http://plane.invalid",
        "token",
        verify_ssl=False,
        max_rate_limit_retries=2,
        rate_limit_backoff_seconds=0.01,
    )
    attempts = {"count": 0}

    def fake_open(request, timeout):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise plane.urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=None,
            )

        class _Response:
            status = 200

            def read(self):
                return b'{"ok": true}'

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        return _Response()

    monkeypatch.setattr(client._opener, "open", fake_open)
    sleeps: list[float] = []
    monkeypatch.setattr(plane.time, "sleep", sleeps.append)

    status, payload = client._request("/api/v1/users/me/")

    assert status == 200
    assert payload == {"ok": True}
    assert attempts["count"] == 3
    assert sleeps == [0.01, 0.02]


def test_plane_client_retries_timeout_requests(monkeypatch) -> None:
    client = plane.PlaneClient(
        "http://plane.invalid",
        "token",
        verify_ssl=False,
        max_rate_limit_retries=2,
        rate_limit_backoff_seconds=0.01,
    )
    attempts = {"count": 0}

    def fake_open(request, timeout):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise TimeoutError("timed out")

        class _Response:
            status = 200

            def read(self):
                return b'{"ok": true}'

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        return _Response()

    monkeypatch.setattr(client._opener, "open", fake_open)
    sleeps: list[float] = []
    monkeypatch.setattr(plane.time, "sleep", sleeps.append)

    status, payload = client._request("/api/v1/users/me/")

    assert status == 200
    assert payload == {"ok": True}
    assert attempts["count"] == 3
    assert sleeps == [0.01, 0.02]


def test_plane_client_retries_transient_server_errors(monkeypatch) -> None:
    client = plane.PlaneClient(
        "http://plane.invalid",
        "token",
        verify_ssl=False,
        max_rate_limit_retries=2,
        rate_limit_backoff_seconds=0.01,
    )
    attempts = {"count": 0}

    def fake_open(request, timeout):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise plane.urllib.error.HTTPError(
                request.full_url,
                502,
                "Bad Gateway",
                hdrs=None,
                fp=None,
            )

        class _Response:
            status = 200

            def read(self):
                return b'{"ok": true}'

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        return _Response()

    monkeypatch.setattr(client._opener, "open", fake_open)
    sleeps: list[float] = []
    monkeypatch.setattr(plane.time, "sleep", sleeps.append)

    status, payload = client._request("/api/v1/users/me/")

    assert status == 200
    assert payload == {"ok": True}
    assert attempts["count"] == 3
    assert sleeps == [0.01, 0.02]


def test_sync_adrs_reuses_issue_index_for_repo_adr_updates(tmp_path, monkeypatch) -> None:
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "base_url": "http://plane.invalid",
                "api_token": "token",
                "workspace_slug": "lv3-platform",
                "project_id": "project-1",
                "verify_ssl": False,
            }
        )
    )
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    adr_path = adr_dir / "0193-plane-kanban-task-board.md"
    adr_path.write_text(
        "\n".join(
            [
                "# ADR 0193: Plane Kanban Task Board",
                "",
                "- Status: Accepted",
                "- Implementation Status: Implemented",
                "",
                "## Context",
                "",
                "Track ADRs in Plane.",
            ]
        )
    )

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.list_issues_calls = 0
            self.timeout = kwargs["timeout"]
            self.max_rate_limit_retries = kwargs["max_rate_limit_retries"]

        def verify_api_key(self):
            return True

        def list_states(self, workspace_slug, project_id):
            return [{"name": "Done", "id": "state-done"}]

        def list_issues(self, workspace_slug, project_id):
            self.list_issues_calls += 1
            return [{"id": "issue-1", "external_source": "repo_adr", "external_id": "adr-0193"}]

        def update_issue(self, workspace_slug, project_id, issue_id, payload):
            return {"id": issue_id, "name": payload["name"], "state_id": payload["state_id"]}

    captured: dict[str, FakeClient] = {}

    def fake_plane_client(*args, **kwargs):
        client = FakeClient(*args, **kwargs)
        captured["client"] = client
        return client

    monkeypatch.setattr(sync_adrs_to_plane, "PlaneClient", fake_plane_client)

    summary = sync_adrs_to_plane.sync_adrs(auth_file=str(auth_file), adr_dir=str(adr_dir))

    assert summary["count"] == 1
    assert summary["synced"][0]["issue_id"] == "issue-1"
    assert captured["client"].list_issues_calls == 1
    assert captured["client"].timeout == 120
    assert captured["client"].max_rate_limit_retries == 8


def test_ensure_issue_for_adr_skips_patch_when_issue_already_matches() -> None:
    record = plane.AdrRecord(
        adr_id="0193",
        title="Plane Kanban Task Board",
        status="Accepted",
        implementation_status="Partial",
        path=Path("docs/adr/0193-plane-kanban-task-board.md"),
        summary="Track ADRs in Plane.",
    )

    class FakeClient:
        def update_issue(self, *args, **kwargs):
            raise AssertionError("update_issue should not be called when the issue is already current")

    existing_issue = {
        "id": "issue-1",
        "name": "ADR 0193: Plane Kanban Task Board",
        "description_html": plane.render_adr_description(record),
        "state": "state-todo",
    }

    issue = plane.ensure_issue_for_adr(
        FakeClient(),
        workspace_slug="lv3-platform",
        project_id="project-1",
        states_by_name={"Todo": "state-todo"},
        record=record,
        existing_issue=existing_issue,
    )

    assert issue is existing_issue
