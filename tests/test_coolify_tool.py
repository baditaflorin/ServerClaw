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


def test_ensure_application_omits_domains_for_dockercompose(monkeypatch, tmp_path: Path) -> None:
    client = make_client(tmp_path)
    create_payloads: list[dict[str, Any]] = []
    application_calls = {"count": 0}

    def fake_create_private_deploy_key_application(payload: dict[str, Any]) -> str:
        create_payloads.append(payload)
        return "app-123"

    def fake_applications() -> list[dict[str, Any]]:
        application_calls["count"] += 1
        if application_calls["count"] == 1:
            return []
        return [{"uuid": "app-123", "name": "education-wemeshup"}]

    monkeypatch.setattr(client, "create_private_deploy_key_application", fake_create_private_deploy_key_application)
    monkeypatch.setattr(client, "applications", fake_applications)

    application = client.ensure_application(
        app_name="education-wemeshup",
        project_uuid="project-1",
        environment_name="production",
        server_uuid="server-1",
        destination_uuid="dest-1",
        repo="git@github.com:baditaflorin/education_wemeshup.git",
        branch="main",
        build_pack="dockercompose",
        ports_exposes="80",
        base_directory="/",
        domains=[],
        source="private-deploy-key",
        private_key_uuid="key-1",
        docker_compose_location="/compose.yaml",
        docker_compose_domains=[{"name": "catalog-web", "domain": "https://education-wemeshup.apps.lv3.org"}],
    )

    assert application["uuid"] == "app-123"
    assert "domains" not in create_payloads[0]
    assert create_payloads[0]["docker_compose_location"] == "/compose.yaml"


def test_ensure_application_omits_private_key_uuid_on_update(monkeypatch, tmp_path: Path) -> None:
    client = make_client(tmp_path)
    captured: dict[str, Any] = {}

    monkeypatch.setattr(client, "applications", lambda: [{"uuid": "app-123", "name": "education-wemeshup"}])

    def fake_update_application(application_uuid: str, payload: dict[str, Any]) -> None:
        captured["application_uuid"] = application_uuid
        captured["payload"] = payload

    monkeypatch.setattr(client, "update_application", fake_update_application)

    application = client.ensure_application(
        app_name="education-wemeshup",
        project_uuid="project-1",
        environment_name="production",
        server_uuid="server-1",
        destination_uuid="dest-1",
        repo="git@github.com:baditaflorin/education_wemeshup.git",
        branch="main",
        build_pack="dockercompose",
        ports_exposes="80",
        base_directory="/",
        domains=[],
        source="private-deploy-key",
        private_key_uuid="key-1",
        docker_compose_location="/compose.yaml",
        docker_compose_domains=[{"name": "catalog-web", "domain": "https://education-wemeshup.apps.lv3.org"}],
    )

    assert application["uuid"] == "app-123"
    assert captured["application_uuid"] == "app-123"
    assert "private_key_uuid" not in captured["payload"]
    assert captured["payload"]["docker_compose_location"] == "/compose.yaml"


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


def test_resolve_source_auto_treats_ssh_repositories_as_private() -> None:
    assert tool.resolve_source("auto", "git@github.com:baditaflorin/education_wemeshup.git") == "private-deploy-key"
    assert tool.resolve_source("auto", "https://github.com/coollabsio/coolify-examples") == "public"
    assert tool.resolve_source("public", "git@github.com:baditaflorin/education_wemeshup.git") == "public"


def test_private_repo_url_converts_github_https_to_ssh() -> None:
    assert (
        tool.private_repo_url("https://github.com/baditaflorin/education_wemeshup.git", "baditaflorin/education_wemeshup")
        == "git@github.com:baditaflorin/education_wemeshup.git"
    )


def test_parse_compose_domain_mapping_normalizes_domain() -> None:
    assert tool.parse_compose_domain_mapping("catalog-web=education-wemeshup.apps.lv3.org") == {
        "name": "catalog-web",
        "domain": "https://education-wemeshup.apps.lv3.org",
    }


def test_normalize_repo_location_adds_leading_slash() -> None:
    assert tool.normalize_repo_location("compose.yaml") == "/compose.yaml"
    assert tool.normalize_repo_location("/docker/frontend.Dockerfile") == "/docker/frontend.Dockerfile"
    assert tool.normalize_repo_location(None) is None


def test_ensure_github_deploy_key_ignores_public_key_comment(monkeypatch, tmp_path: Path) -> None:
    public_key_path = tmp_path / "deploy-key.pub"
    public_key_path.write_text("ssh-ed25519 AAAATEST coolify:repo\n", encoding="utf-8")

    monkeypatch.setattr(
        tool,
        "github_deploy_keys",
        lambda repo_slug: [{"id": 7, "title": "coolify-repo", "key": "ssh-ed25519 AAAATEST", "read_only": True}],
    )
    monkeypatch.setattr(tool, "run_command", lambda command: None)

    entry = tool.ensure_github_deploy_key(
        repo_slug="baditaflorin/education_wemeshup",
        title="coolify-repo",
        public_key_path=public_key_path,
    )

    assert entry["id"] == 7


def test_command_deploy_repo_bootstraps_private_deploy_key(monkeypatch, tmp_path: Path, capsys) -> None:
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
            return {"uuid": "server-1", "name": "coolify-lv3"}

        def ensure_private_key(self, *, name: str, description: str, private_key: str) -> dict[str, Any]:
            captured["coolify_private_key_request"] = {
                "name": name,
                "description": description,
                "private_key": private_key,
            }
            return {"uuid": "key-1", "name": name}

        def ensure_application(self, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"uuid": "app-1", "name": kwargs["app_name"]}

        def deploy_application(self, application_uuid: str, *, force: bool = False) -> str:
            captured["deploy_application"] = {"application_uuid": application_uuid, "force": force}
            return "deploy-1"

        def deployment(self, deployment_uuid: str) -> dict[str, Any]:
            return {"status": "finished", "deployment_uuid": deployment_uuid}

    def fake_ensure_local_keypair(*, key_path: Path, comment: str) -> tuple[Path, Path]:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text("PRIVATE KEY\n", encoding="utf-8")
        public_key_path = Path(f"{key_path}.pub")
        public_key_path.write_text("ssh-ed25519 AAAATEST\n", encoding="utf-8")
        captured["local_keypair"] = {"key_path": str(key_path), "comment": comment}
        return key_path, public_key_path

    def fake_ensure_github_deploy_key(*, repo_slug: str, title: str, public_key_path: Path) -> dict[str, Any]:
        captured["github_deploy_key_request"] = {
            "repo_slug": repo_slug,
            "title": title,
            "public_key_path": str(public_key_path),
        }
        return {"id": 42, "title": title, "read_only": True}

    monkeypatch.setattr(tool, "CoolifyClient", FakeClient)
    monkeypatch.setattr(tool, "ensure_local_keypair", fake_ensure_local_keypair)
    monkeypatch.setattr(tool, "ensure_github_deploy_key", fake_ensure_github_deploy_key)

    exit_code = tool.main(
        [
            "--auth-file",
            str(auth_path),
            "deploy-repo",
            "--repo",
            "git@github.com:baditaflorin/education_wemeshup.git",
            "--branch",
            "main",
            "--source",
            "private-deploy-key",
            "--app-name",
            "education-wemeshup",
            "--build-pack",
            "dockercompose",
            "--docker-compose-location",
            "compose.yaml",
            "--compose-domain",
            "catalog-web=education-wemeshup.apps.lv3.org",
            "--wait",
            "--timeout",
            "60",
            "--deploy-key-path",
            str(tmp_path / "education-wemeshup.ed25519"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["local_keypair"]["comment"] == "coolify:baditaflorin/education_wemeshup"
    assert captured["github_deploy_key_request"]["repo_slug"] == "baditaflorin/education_wemeshup"
    assert captured["coolify_private_key_request"]["name"] == "coolify-baditaflorin-education-wemeshup"
    assert captured["repo"] == "git@github.com:baditaflorin/education_wemeshup.git"
    assert captured["source"] == "private-deploy-key"
    assert captured["private_key_uuid"] == "key-1"
    assert captured["docker_compose_location"] == "/compose.yaml"
    assert captured["docker_compose_domains"] == [
        {"name": "catalog-web", "domain": "https://education-wemeshup.apps.lv3.org"}
    ]
    assert captured["domains"] == []
    assert output["source"] == "private-deploy-key"
    assert output["repository"] == "git@github.com:baditaflorin/education_wemeshup.git"
    assert output["domains"] == ["https://education-wemeshup.apps.lv3.org"]
    assert output["compose_domains"] == [
        {"name": "catalog-web", "domain": "https://education-wemeshup.apps.lv3.org"}
    ]
    assert output["github_deploy_key"]["title"] == "coolify-baditaflorin-education-wemeshup"
    assert output["coolify_private_key"]["uuid"] == "key-1"
