from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

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
        assert body == {"domains": "http://repo-smoke.apps.example.com"}
        return DummyResponse(200, {"uuid": "app-123"})

    monkeypatch.setattr(tool.urllib.request, "urlopen", fake_urlopen)

    client.update_application("app-123", {"domains": "http://repo-smoke.apps.example.com"})


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
        docker_compose_domains=[{"name": "catalog-web", "domain": "https://education-wemeshup.apps.example.com"}],
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
        docker_compose_domains=[{"name": "catalog-web", "domain": "https://education-wemeshup.apps.example.com"}],
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
                "name": "coolify",
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
    assert captured["domains"] == ["http://repo-smoke.apps.example.com"]
    assert captured["deploy_application"] == {"application_uuid": "app-1", "force": False}
    assert captured["repo"] == "coollabsio/coolify-examples"
    assert output["domains"] == ["http://repo-smoke.apps.example.com"]
    assert output["status"] == "finished"


def test_normalize_repository_strips_github_url_prefixes() -> None:
    assert tool.normalize_repository("https://github.com/coollabsio/coolify-examples") == "coollabsio/coolify-examples"
    assert (
        tool.normalize_repository("https://github.com/coollabsio/coolify-examples.git") == "coollabsio/coolify-examples"
    )
    assert tool.normalize_repository("git@github.com:coollabsio/coolify-examples.git") == "coollabsio/coolify-examples"


def test_resolve_source_auto_treats_ssh_repositories_as_private() -> None:
    assert tool.resolve_source("auto", "git@github.com:baditaflorin/education_wemeshup.git") == "private-deploy-key"
    assert tool.resolve_source("auto", "https://github.com/coollabsio/coolify-examples") == "public"
    assert tool.resolve_source("public", "git@github.com:baditaflorin/education_wemeshup.git") == "public"


def test_private_repo_url_converts_github_https_to_ssh() -> None:
    assert (
        tool.private_repo_url(
            "https://github.com/baditaflorin/education_wemeshup.git", "baditaflorin/education_wemeshup"
        )
        == "git@github.com:baditaflorin/education_wemeshup.git"
    )


def test_parse_compose_domain_mapping_normalizes_domain() -> None:
    assert tool.parse_compose_domain_mapping("catalog-web=education-wemeshup.apps.example.com") == {
        "name": "catalog-web",
        "domain": "https://education-wemeshup.apps.example.com",
    }


def test_transient_deployment_failure_reason_detects_registry_timeout() -> None:
    deployment = {
        "status": "failed",
        "logs": json.dumps(
            [
                {
                    "output": 'failed to fetch anonymous token: Get "https://auth.docker.io/token": dial tcp 104.18.43.178:443: i/o timeout'
                }
            ]
        ),
    }

    assert tool.transient_deployment_failure_reason(deployment) == "docker-registry-auth-timeout"


def test_transient_deployment_failure_reason_detects_go_proxy_timeout() -> None:
    deployment = {
        "status": "failed",
        "logs": json.dumps(
            [
                {
                    "output": 'go: dario.cat/mergo@v1.0.1: Get "https://proxy.golang.org/dario.cat/mergo/@v/v1.0.1.mod": dial tcp: lookup proxy.golang.org on 1.1.1.1:53: read udp 172.17.0.4:46641->1.1.1.1:53: i/o timeout'
                }
            ]
        ),
    }

    assert tool.transient_deployment_failure_reason(deployment) == "upstream-registry-timeout"


def test_transient_deployment_failure_reason_detects_npm_cli_abrupt_exit() -> None:
    deployment = {
        "status": "failed",
        "logs": json.dumps(
            [
                {"command": "npm ci --no-audit --no-fund --loglevel=warn"},
                {"output": "npm error Exit handler never called!"},
            ]
        ),
    }

    assert tool.transient_deployment_failure_reason(deployment) == "npm-cli-abrupt-exit"


def test_cancel_active_deployments_for_application_cancels_only_queued_and_in_progress(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    cancelled: list[str] = []

    def fake_deployments() -> list[dict[str, Any]]:
        return [
            {"application_name": "education-wemeshup", "deployment_uuid": "deploy-queued", "status": "queued"},
            {"application_name": "education-wemeshup", "deployment_uuid": "deploy-running", "status": "in_progress"},
            {"application_name": "education-wemeshup", "deployment_uuid": "deploy-finished", "status": "finished"},
            {"application_name": "repo-smoke", "deployment_uuid": "deploy-other", "status": "queued"},
        ]

    def fake_cancel_deployment(deployment_uuid: str) -> dict[str, Any]:
        cancelled.append(deployment_uuid)
        return {"deployment_uuid": deployment_uuid, "status": "cancelled-by-user"}

    client.deployments = fake_deployments  # type: ignore[method-assign]
    client.cancel_deployment = fake_cancel_deployment  # type: ignore[method-assign]

    result = tool.cancel_active_deployments_for_application(client, application_name="education-wemeshup")

    assert cancelled == ["deploy-queued", "deploy-running"]
    assert result == [
        {
            "deployment_uuid": "deploy-queued",
            "previous_status": "queued",
            "status": "cancelled-by-user",
        },
        {
            "deployment_uuid": "deploy-running",
            "previous_status": "in_progress",
            "status": "cancelled-by-user",
        },
    ]


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
            return {"uuid": "server-1", "name": "coolify"}

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
            "catalog-web=education-wemeshup.apps.example.com",
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
        {"name": "catalog-web", "domain": "https://education-wemeshup.apps.example.com"}
    ]
    assert captured["domains"] == []
    assert output["source"] == "private-deploy-key"
    assert output["repository"] == "git@github.com:baditaflorin/education_wemeshup.git"
    assert output["domains"] == ["https://education-wemeshup.apps.example.com"]
    assert output["compose_domains"] == [
        {"name": "catalog-web", "domain": "https://education-wemeshup.apps.example.com"}
    ]
    assert output["github_deploy_key"]["title"] == "coolify-baditaflorin-education-wemeshup"
    assert output["coolify_private_key"]["uuid"] == "key-1"


def test_command_deploy_repo_retries_transient_failures(monkeypatch, tmp_path: Path, capsys) -> None:
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

    deploy_calls: list[dict[str, Any]] = []

    class FakeClient:
        def __init__(self, auth: dict[str, Any]) -> None:
            self.auth = auth

        def ensure_project(self, name: str, description: str | None = None) -> dict[str, Any]:
            return {"uuid": "project-1", "name": name}

        def ensure_environment(self, project_uuid: str, environment_name: str) -> dict[str, Any]:
            return {"uuid": "env-1", "name": environment_name}

        def resolve_server(self, server_uuid: str | None) -> dict[str, Any]:
            return {"uuid": "server-1", "name": "coolify"}

        def ensure_application(self, **kwargs: Any) -> dict[str, Any]:
            return {"uuid": "app-1", "name": kwargs["app_name"]}

        def deploy_application(self, application_uuid: str, *, force: bool = False) -> str:
            deploy_calls.append({"application_uuid": application_uuid, "force": force})
            return f"deploy-{len(deploy_calls)}"

        def deployment(self, deployment_uuid: str) -> dict[str, Any]:
            if deployment_uuid == "deploy-1":
                return {
                    "status": "failed",
                    "logs": [
                        {
                            "output": 'failed to fetch anonymous token: Get "https://auth.docker.io/token": dial tcp 104.18.43.178:443: i/o timeout'
                        }
                    ],
                }
            return {"status": "finished", "deployment_uuid": deployment_uuid}

    monkeypatch.setattr(tool, "CoolifyClient", FakeClient)
    monkeypatch.setattr(tool.time, "sleep", lambda seconds: None)

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
            "--retry-delay",
            "0",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert deploy_calls == [
        {"application_uuid": "app-1", "force": False},
        {"application_uuid": "app-1", "force": False},
    ]
    assert output["status"] == "finished"
    assert output["deployment_uuid"] == "deploy-2"
    assert output["attempts"] == [
        {
            "attempt": 1,
            "deployment_uuid": "deploy-1",
            "status": "failed",
            "retry_reason": "docker-registry-auth-timeout",
        },
        {
            "attempt": 2,
            "deployment_uuid": "deploy-2",
            "status": "finished",
        },
    ]


def test_command_deploy_repo_cancels_active_deployments_before_redeploy(monkeypatch, tmp_path: Path, capsys) -> None:
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

    cancelled: list[str] = []
    deploy_calls: list[dict[str, Any]] = []

    class FakeClient:
        def __init__(self, auth: dict[str, Any]) -> None:
            self.auth = auth

        def ensure_project(self, name: str, description: str | None = None) -> dict[str, Any]:
            return {"uuid": "project-1", "name": name}

        def ensure_environment(self, project_uuid: str, environment_name: str) -> dict[str, Any]:
            return {"uuid": "env-1", "name": environment_name}

        def resolve_server(self, server_uuid: str | None) -> dict[str, Any]:
            return {"uuid": "server-1", "name": "coolify"}

        def ensure_application(self, **kwargs: Any) -> dict[str, Any]:
            return {"uuid": "app-1", "name": kwargs["app_name"]}

        def deployments(self) -> list[dict[str, Any]]:
            return [
                {"application_name": "education-wemeshup", "deployment_uuid": "deploy-old", "status": "queued"},
                {"application_name": "repo-smoke", "deployment_uuid": "deploy-other", "status": "queued"},
            ]

        def cancel_deployment(self, deployment_uuid: str) -> dict[str, Any]:
            cancelled.append(deployment_uuid)
            return {"deployment_uuid": deployment_uuid, "status": "cancelled-by-user"}

        def deploy_application(self, application_uuid: str, *, force: bool = False) -> str:
            deploy_calls.append({"application_uuid": application_uuid, "force": force})
            return "deploy-new"

        def deployment(self, deployment_uuid: str) -> dict[str, Any]:
            return {"status": "finished", "deployment_uuid": deployment_uuid}

    monkeypatch.setattr(tool, "CoolifyClient", FakeClient)

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
            "catalog-web=education-wemeshup.apps.example.com",
            "--private-key-uuid",
            "key-1",
            "--wait",
            "--timeout",
            "60",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert cancelled == ["deploy-old"]
    assert deploy_calls == [{"application_uuid": "app-1", "force": False}]
    assert output["cancelled_deployments"] == [
        {
            "deployment_uuid": "deploy-old",
            "previous_status": "queued",
            "status": "cancelled-by-user",
        }
    ]


# ---------------------------------------------------------------------------
# ADR 0340: register-deployment-server and migrate-deployment-server
# ---------------------------------------------------------------------------


def test_register_deployment_server_creates_new_server(monkeypatch, tmp_path: Path, capsys) -> None:
    """register-deployment-server posts a new server when name is not already registered."""
    client = make_client(tmp_path)
    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"controller_url": "http://127.0.0.1:8000", "api_token": "tok"}', encoding="utf-8")

    call_log: list[tuple[str, str]] = []

    def fake_request(self, method: str, path: str, payload=None, **kwargs):  # type: ignore
        call_log.append((method, path))
        if path == "/api/v1/servers" and method == "GET":
            return []  # no existing servers
        if path == "/api/v1/security/keys" and method == "GET":
            return [{"uuid": "key-1", "name": "default"}]
        if path == "/api/v1/servers" and method == "POST":
            assert payload["name"] == "coolify-apps"
            assert payload["ip"] == "10.10.10.71"
            return {"uuid": "srv-new", "name": "coolify-apps"}
        raise AssertionError(f"unexpected {method} {path}")

    monkeypatch.setattr(tool.CoolifyClient, "_request", fake_request)

    exit_code = tool.main(
        [
            "--auth-file",
            str(auth_file),
            "register-deployment-server",
            "--host",
            "coolify-apps",
            "--ip",
            "10.10.10.71",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert out["status"] == "registered"


def test_register_deployment_server_is_idempotent(monkeypatch, tmp_path: Path, capsys) -> None:
    """register-deployment-server exits 0 without creating a duplicate when name already exists."""
    client = make_client(tmp_path)
    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"controller_url": "http://127.0.0.1:8000", "api_token": "tok"}', encoding="utf-8")
    post_called = {"count": 0}

    def fake_request(self, method: str, path: str, payload=None, **kwargs):  # type: ignore
        if path == "/api/v1/servers" and method == "GET":
            return [{"uuid": "srv-existing", "name": "coolify-apps", "ip": "10.10.10.71"}]
        if method == "POST":
            post_called["count"] += 1
        return {}

    monkeypatch.setattr(tool.CoolifyClient, "_request", fake_request)

    exit_code = tool.main(
        [
            "--auth-file",
            str(auth_file),
            "register-deployment-server",
            "--host",
            "coolify-apps",
            "--ip",
            "10.10.10.71",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert out["status"] == "already_registered"
    assert post_called["count"] == 0


def test_migrate_deployment_server_moves_apps(monkeypatch, tmp_path: Path, capsys) -> None:
    """migrate-deployment-server re-assigns applications from source to target server."""
    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"controller_url": "http://127.0.0.1:8000", "api_token": "tok"}', encoding="utf-8")
    patched: list[dict] = []

    def fake_request(self, method: str, path: str, payload=None, **kwargs):  # type: ignore
        if path == "/api/v1/servers" and method == "GET":
            return [
                {"uuid": "src-uuid", "name": "coolify"},
                {"uuid": "dst-uuid", "name": "coolify-apps"},
            ]
        if path == "/api/v1/applications" and method == "GET":
            return [
                {"uuid": "app-1", "name": "smoke-app", "server": {"uuid": "src-uuid"}},
                {"uuid": "app-2", "name": "already-moved", "server": {"uuid": "dst-uuid"}},
            ]
        if method == "PATCH":
            patched.append({"path": path, "payload": payload})
            return {}
        return {}

    monkeypatch.setattr(tool.CoolifyClient, "_request", fake_request)

    exit_code = tool.main(
        [
            "--auth-file",
            str(auth_file),
            "migrate-deployment-server",
            "--from",
            "coolify",
            "--to",
            "coolify-apps",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert "smoke-app" in out["migrated"]
    assert "already-moved" in out["skipped"]
    assert out["migration_count"] == 1
    assert len(patched) == 1
    assert patched[0]["payload"] == {"destination_uuid": "dst-uuid"}


def test_migrate_deployment_server_returns_2_when_nothing_to_migrate(monkeypatch, tmp_path: Path) -> None:
    """migrate-deployment-server exits 2 when all apps are already on the target server."""
    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"controller_url": "http://127.0.0.1:8000", "api_token": "tok"}', encoding="utf-8")

    def fake_request(self, method: str, path: str, payload=None, **kwargs):  # type: ignore
        if path == "/api/v1/servers" and method == "GET":
            return [
                {"uuid": "src-uuid", "name": "coolify"},
                {"uuid": "dst-uuid", "name": "coolify-apps"},
            ]
        if path == "/api/v1/applications" and method == "GET":
            return [{"uuid": "app-1", "name": "already-moved", "server": {"uuid": "dst-uuid"}}]
        return {}

    monkeypatch.setattr(tool.CoolifyClient, "_request", fake_request)

    exit_code = tool.main(
        [
            "--auth-file",
            str(auth_file),
            "migrate-deployment-server",
            "--from",
            "coolify",
            "--to",
            "coolify-apps",
        ]
    )
    assert exit_code == 2


def test_default_deployment_server_reads_from_stack_yaml(tmp_path: Path, monkeypatch) -> None:
    """_default_deployment_server() derives the server name from versions/stack.yaml (ADR 0340 DRY fix)."""
    stack_yaml = tmp_path / "versions" / "stack.yaml"
    stack_yaml.parent.mkdir(parents=True)
    stack_yaml.write_text(
        "observed_state:\n  coolify:\n    deployment_server_name: coolify-apps\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tool, "_STACK_YAML", stack_yaml)
    assert tool._default_deployment_server() == "coolify-apps"


# ---------------------------------------------------------------------------
# ADR 0345: Proxmox guest-exec backed Coolify commands
# ---------------------------------------------------------------------------

_PROXMOX_AUTH = {
    "api_url": "https://proxmox.example.com:8006/api2/json",
    "full_token_id": "lv3-automation@pve!primary",
    "value": "test-secret",
    "authorization_header": "PVEAPIToken=lv3-automation@pve!primary=test-secret",
}

_COOLIFY_AUTH = {
    "controller_url": "http://127.0.0.1:8000",
    "api_token": "token",
}


def _proxmox_auth_file(tmp_path: Path) -> Path:
    """Write a valid Proxmox auth file and return its path."""
    p = tmp_path / "proxmox-auth.json"
    p.write_text(json.dumps(_PROXMOX_AUTH), encoding="utf-8")
    return p


def _coolify_auth_file(tmp_path: Path) -> Path:
    """Write a valid Coolify auth file and return its path."""
    p = tmp_path / "coolify-auth.json"
    p.write_text(json.dumps(_COOLIFY_AUTH), encoding="utf-8")
    return p


class FakeGuestExec:
    """
    Replaces ProxmoxClient.guest_exec with a call-queue.

    Pre-load responses as a list of (exit_code, stdout, stderr) tuples.
    Each call to guest_exec pops the first response.  Calls are recorded in
    self.calls as {"vmid": int, "command": list[str]}.
    """

    def __init__(self, responses: list[tuple[int, str, str]]) -> None:
        self._responses: list[tuple[int, str, str]] = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        vmid: int,
        command: list[str],
        timeout: int = 60,
    ) -> tuple[int, str, str]:
        self.calls.append({"vmid": vmid, "command": list(command)})
        if not self._responses:
            return (0, "", "")
        return self._responses.pop(0)


def _make_fake_proxmox_client(fake_guest_exec: FakeGuestExec, tmp_path: Path) -> Any:
    """Return a fake ProxmoxClient-like object for patching _make_proxmox_client."""
    # Import ProxmoxClient here since it may be available from proxmox_tool
    try:
        import proxmox_tool as ptool

        client = ptool.ProxmoxClient(
            api_url=_PROXMOX_AUTH["api_url"],
            authorization_header=_PROXMOX_AUTH["authorization_header"],
            node="pve",
        )
        client.guest_exec = fake_guest_exec  # type: ignore[method-assign]
        return client
    except ImportError:
        return None


def test_command_db_exec_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """db-exec runs psql inside the VM and returns result JSON."""
    fake = FakeGuestExec([(0, "UPDATE 2\n", "")])

    def fake_make_proxmox_client(proxmox_auth_file: str, node: str = "pve") -> Any:
        client = _make_fake_proxmox_client(fake, tmp_path)
        if client is not None:
            return client

        # Minimal stub if proxmox_tool unavailable
        class Stub:
            def guest_exec(self, vmid, command, timeout=60):
                return fake(vmid, command, timeout)

        return Stub()

    monkeypatch.setattr(tool, "_make_proxmox_client", fake_make_proxmox_client)

    rc = tool.main(
        [
            "--auth-file",
            str(_coolify_auth_file(tmp_path)),
            "db-exec",
            "--proxmox-auth-file",
            str(_proxmox_auth_file(tmp_path)),
            "--vmid",
            "170",
            "--sql",
            "UPDATE applications SET destination_id=34 WHERE destination_id=1",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["exit_code"] == 0
    assert "UPDATE 2" in out["stdout"]
    assert out["container"] == "coolify-db"
    assert out["vmid"] == 170
    # Verify psql command structure
    assert fake.calls[0]["command"][0:3] == ["docker", "exec", "coolify-db"]
    assert "psql" in fake.calls[0]["command"]


def test_command_db_exec_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """db-exec exits 1 when psql returns non-zero."""
    fake = FakeGuestExec([(1, "", "ERROR: relation does not exist\n")])

    def fake_make_proxmox_client(proxmox_auth_file: str, node: str = "pve") -> Any:
        class Stub:
            def guest_exec(self, vmid, command, timeout=60):
                return fake(vmid, command, timeout)

        return Stub()

    monkeypatch.setattr(tool, "_make_proxmox_client", fake_make_proxmox_client)

    rc = tool.main(
        [
            "--auth-file",
            str(_coolify_auth_file(tmp_path)),
            "db-exec",
            "--proxmox-auth-file",
            str(_proxmox_auth_file(tmp_path)),
            "--vmid",
            "170",
            "--sql",
            "SELECT * FROM nonexistent_table",
        ]
    )
    assert rc == 1


def test_command_clear_cache_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """clear-cache runs artisan cache:clear and config:clear and exits 0."""
    fake = FakeGuestExec([(0, "Application cache cleared!\nConfiguration cache cleared!\n", "")])

    def fake_make_proxmox_client(proxmox_auth_file: str, node: str = "pve") -> Any:
        class Stub:
            def guest_exec(self, vmid, command, timeout=60):
                return fake(vmid, command, timeout)

        return Stub()

    monkeypatch.setattr(tool, "_make_proxmox_client", fake_make_proxmox_client)

    rc = tool.main(
        [
            "--auth-file",
            str(_coolify_auth_file(tmp_path)),
            "clear-cache",
            "--proxmox-auth-file",
            str(_proxmox_auth_file(tmp_path)),
            "--vmid",
            "170",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["container"] == "coolify"
    # Verify artisan commands are in the shell script
    assert "cache:clear" in fake.calls[0]["command"][-1]


def test_command_migrate_apps_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """migrate-apps finds destination IDs, updates the DB, and clears cache."""
    fake = FakeGuestExec(
        [
            (0, "1", ""),  # from_id lookup
            (0, "34", ""),  # to_id lookup
            (0, "2", ""),  # count
            (0, "repo-smoke\neducation-wemeshup", ""),  # app names
            (0, "UPDATE 2", ""),  # migration UPDATE
            (0, "Application cache cleared!", ""),  # cache clear
        ]
    )

    def fake_make_proxmox_client(proxmox_auth_file: str, node: str = "pve") -> Any:
        class Stub:
            def guest_exec(self, vmid, command, timeout=60):
                return fake(vmid, command, timeout)

        return Stub()

    monkeypatch.setattr(tool, "_make_proxmox_client", fake_make_proxmox_client)

    rc = tool.main(
        [
            "--auth-file",
            str(_coolify_auth_file(tmp_path)),
            "migrate-apps",
            "--proxmox-auth-file",
            str(_proxmox_auth_file(tmp_path)),
            "--vmid",
            "170",
            "--from",
            "coolify",
            "--to",
            "coolify-apps",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "migrated"
    assert out["from_destination_id"] == 1
    assert out["to_destination_id"] == 34
    assert out["migrated_count"] == 2
    assert "repo-smoke" in out["migrated_apps"]
    assert "education-wemeshup" in out["migrated_apps"]
    assert len(fake.calls) == 6


def test_command_migrate_apps_noop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """migrate-apps exits 2 (no-op) when count == 0."""
    fake = FakeGuestExec(
        [
            (0, "1", ""),  # from_id
            (0, "34", ""),  # to_id
            (0, "0", ""),  # count == 0
        ]
    )

    def fake_make_proxmox_client(proxmox_auth_file: str, node: str = "pve") -> Any:
        class Stub:
            def guest_exec(self, vmid, command, timeout=60):
                return fake(vmid, command, timeout)

        return Stub()

    monkeypatch.setattr(tool, "_make_proxmox_client", fake_make_proxmox_client)

    rc = tool.main(
        [
            "--auth-file",
            str(_coolify_auth_file(tmp_path)),
            "migrate-apps",
            "--proxmox-auth-file",
            str(_proxmox_auth_file(tmp_path)),
            "--vmid",
            "170",
            "--from",
            "coolify",
            "--to",
            "coolify-apps",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["status"] == "nothing_to_migrate"
    assert out["migrated_count"] == 0
    assert len(fake.calls) == 3  # no UPDATE or cache clear


def test_command_install_deploy_key_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """install-deploy-key installs the key into authorized_keys on the target VM."""
    pubkey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC0gB481 coolify-deploy"
    fake = FakeGuestExec(
        [
            (0, "", ""),  # no existing keys
            (0, "", ""),  # append script
        ]
    )

    def fake_make_proxmox_client(proxmox_auth_file: str, node: str = "pve") -> Any:
        class Stub:
            def guest_exec(self, vmid, command, timeout=60):
                return fake(vmid, command, timeout)

        return Stub()

    monkeypatch.setattr(tool, "_make_proxmox_client", fake_make_proxmox_client)

    rc = tool.main(
        [
            "--auth-file",
            str(_coolify_auth_file(tmp_path)),
            "install-deploy-key",
            "--proxmox-auth-file",
            str(_proxmox_auth_file(tmp_path)),
            "--vmid",
            "171",
            "--pubkey",
            pubkey,
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "installed"
    assert out["key_fingerprint"] == "coolify-deploy"
    assert out["vmid"] == 171
    # Second call should be the bash append script
    assert fake.calls[1]["command"][0] == "bash"
