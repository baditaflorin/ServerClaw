from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import coolify_tool as tool


class DummyResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    def __enter__(self) -> "DummyResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        if isinstance(self._payload, bytes):
            return self._payload
        if isinstance(self._payload, str):
            return self._payload.encode("utf-8")
        return json.dumps(self._payload).encode("utf-8")


def make_client(tmp_path: Path) -> tool.CoolifyClient:
    auth = {
        "controller_url": "http://127.0.0.1:8000",
        "api_token": "token",
    }
    client = tool.CoolifyClient(auth)
    client.bootstrap_key_file = tmp_path / "bootstrap-key"
    client.bootstrap_key_file.write_text("placeholder\n", encoding="utf-8")
    return client


def test_update_application_accepts_live_patch_status_200(monkeypatch, tmp_path: Path) -> None:
    client = make_client(tmp_path)

    def fake_urlopen(request, timeout=30, context=None):  # type: ignore[no-untyped-def]
        assert request.method == "PATCH"
        assert request.full_url == "http://127.0.0.1:8000/api/v1/applications/app-123"
        body = json.loads(request.data.decode("utf-8"))
        assert body == {"domains": "http://repo-smoke.apps.lv3.org"}
        return DummyResponse(200, {"uuid": "app-123"})

    monkeypatch.setattr(tool.urllib.request, "urlopen", fake_urlopen)

    client.update_application("app-123", {"domains": "http://repo-smoke.apps.lv3.org"})


def test_command_deploy_repo_uses_subdomain_when_domain_not_set(monkeypatch, tmp_path: Path, capsys) -> None:
    auth_path = tmp_path / "admin-auth.json"
    auth_path.write_text(
        json.dumps(
            {
                "controller_url": "http://127.0.0.1:8000",
                "api_token": "token",
                "destination_uuid": "dest-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, auth: dict[str, Any]) -> None:
            self.auth = auth

        def ensure_project(self, name: str, description: str | None = None) -> dict[str, Any]:
            return {"uuid": "project-1", "name": name}

        def ensure_environment(self, project_uuid: str, environment_name: str) -> dict[str, Any]:
            return {"uuid": "env-1", "name": environment_name}

        def resolve_server(self, server_uuid: str | None) -> dict[str, Any]:
            return {
                "uuid": "server-1",
                "name": "coolify-lv3",
                "destinations": [{"uuid": "dest-1"}],
            }

        def ensure_application(self, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"uuid": "app-1", "name": kwargs["app_name"]}

        def deploy_application(self, application_uuid: str, *, force: bool = False) -> str:
            captured["deploy_application"] = {"application_uuid": application_uuid, "force": force}
            return "deploy-1"

        def deployment(self, deployment_uuid: str) -> dict[str, Any]:
            return {"status": "finished", "deployment_uuid": deployment_uuid}

    monkeypatch.setattr(tool, "CoolifyClient", FakeClient)

    exit_code = tool.main(
        [
            "--auth-file",
            str(auth_path),
            "deploy-repo",
            "--repo",
            "https://github.com/coollabsio/coolify-examples",
            "--branch",
            "main",
            "--base-directory",
            "/static",
            "--app-name",
            "repo-smoke",
            "--build-pack",
            "static",
            "--subdomain",
            "repo-smoke",
            "--wait",
            "--timeout",
            "60",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["domains"] == ["http://repo-smoke.apps.lv3.org"]
    assert captured["deploy_application"] == {"application_uuid": "app-1", "force": False}
    assert captured["repo"] == "coollabsio/coolify-examples"
    assert output["domains"] == ["http://repo-smoke.apps.lv3.org"]
    assert output["status"] == "finished"


def test_normalize_repository_strips_github_url_prefixes() -> None:
    assert tool.normalize_repository("https://github.com/coollabsio/coolify-examples") == "coollabsio/coolify-examples"
    assert tool.normalize_repository("https://github.com/coollabsio/coolify-examples.git") == "coollabsio/coolify-examples"
    assert tool.normalize_repository("git@github.com:coollabsio/coolify-examples.git") == "coollabsio/coolify-examples"
