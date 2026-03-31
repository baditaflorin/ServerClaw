from __future__ import annotations

import json
import subprocess
import urllib.error
from datetime import timedelta
from pathlib import Path

import serverclaw_authz


REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = REPO_ROOT / "config" / "serverclaw-authz" / "bootstrap.json"
MODEL_PATH = REPO_ROOT / "config" / "serverclaw-authz" / "model.json"


def test_module_exposes_a_utc_timezone_constant() -> None:
    assert serverclaw_authz.UTC.utcoffset(None) == timedelta(0)


def test_bootstrap_config_points_to_stable_repo_managed_principals() -> None:
    config = json.loads(BOOTSTRAP_PATH.read_text(encoding="utf-8"))

    assert config["store"]["name"] == "serverclaw-authz"
    assert config["principals"]["operator"]["principal"] == "principal:keycloak-user__florin.badita"
    assert config["principals"]["operator"]["grant_type"] == "declared"
    assert "client_secret_file" not in config["principals"]["operator"]
    assert config["principals"]["runtime"]["principal"] == "principal:keycloak-client__serverclaw-runtime"
    assert any(item["name"] == "unauthorized-client-cannot-read-data-scope" for item in config["checks"])


def test_model_covers_workspace_assistant_skill_connector_scope_and_channel() -> None:
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    type_names = {item["type"] for item in model["type_definitions"]}

    assert type_names == {"principal", "workspace", "assistant", "skill", "connector", "data_scope", "channel"}
    channel = next(item for item in model["type_definitions"] if item["type"] == "channel")
    assert "can_send" in channel["relations"]
    assert "can_receive" in channel["relations"]


def test_normalize_model_payload_strips_runtime_only_fields() -> None:
    payload = {
        "id": "ignored",
        "schema_version": "1.1",
        "type_definitions": [
            {
                "type": "user",
                "relations": {},
                "metadata": {
                    "relations": {
                        "reader": {
                            "directly_related_user_types": [{"type": "principal", "condition": ""}],
                            "module": "",
                            "source_info": None,
                        }
                    },
                    "module": "",
                    "source_info": None,
                },
            }
        ],
        "conditions": {},
    }

    normalized = serverclaw_authz.normalize_model_payload(payload)

    assert "id" not in normalized
    assert normalized["type_definitions"][0]["metadata"]["relations"]["reader"]["directly_related_user_types"] == [
        {"type": "principal"}
    ]


def test_build_report_marks_failed_checks() -> None:
    config = json.loads(BOOTSTRAP_PATH.read_text(encoding="utf-8"))
    report = serverclaw_authz.build_report(
        config,
        mode="verify",
        openfga_url="http://100.64.0.1:8014",
        store_id="store-id",
        store_created=False,
        model_id="model-id",
        model_changed=False,
        principal_reports=[],
        check_results=[{"name": "demo", "passed": False}],
    )

    assert report["changed"] is False
    assert report["verification_passed"] is False


def test_declared_principal_verification_uses_the_stable_keycloak_username_reference() -> None:
    report = serverclaw_authz.verify_keycloak_principal(
        "https://sso.lv3.org",
        serverclaw_authz.KeycloakPrincipal(
            name="operator",
            principal="principal:keycloak-user__florin.badita",
            grant_type="declared",
            expected_claims={},
            username="florin.badita",
        ),
    )

    assert report["verification"] == "declared_principal"
    assert report["claims"]["preferred_username"] == "florin.badita"


def test_http_json_retries_transient_transport_failures(monkeypatch) -> None:
    attempts = {"count": 0}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b'{"status":"ok"}'

    def fake_urlopen(request, timeout=None):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise urllib.error.URLError(TimeoutError("timed out"))
        return FakeResponse()

    monkeypatch.setattr(serverclaw_authz.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(serverclaw_authz.time, "sleep", lambda *_args, **_kwargs: None)

    status, payload = serverclaw_authz.http_json("GET", "http://example.invalid/healthz")

    assert attempts["count"] == 3
    assert status == 200
    assert payload == {"status": "ok"}


def test_repo_path_uses_the_shared_repo_root_for_worktree_local_artifacts(monkeypatch, tmp_path: Path) -> None:
    shared_root = tmp_path / "repo"
    worktree_root = shared_root / ".worktrees" / "ws-0262"
    shared_root.mkdir()
    worktree_root.mkdir(parents=True)

    monkeypatch.setattr(serverclaw_authz, "REPO_ROOT", worktree_root)
    monkeypatch.setattr(serverclaw_authz, "COMMON_REPO_ROOT", shared_root)

    assert serverclaw_authz.repo_path(".local/openfga/preshared-key.txt") == (
        shared_root / ".local" / "openfga" / "preshared-key.txt"
    )


def test_repo_path_prefers_the_worktree_for_tracked_repo_files(monkeypatch, tmp_path: Path) -> None:
    shared_root = tmp_path / "repo"
    worktree_root = shared_root / ".worktrees" / "ws-0262"
    tracked_file = worktree_root / "config" / "serverclaw-authz" / "bootstrap.json"
    tracked_file.parent.mkdir(parents=True)
    tracked_file.write_text("{}", encoding="utf-8")
    shared_root.mkdir(exist_ok=True)

    monkeypatch.setattr(serverclaw_authz, "REPO_ROOT", worktree_root)
    monkeypatch.setattr(serverclaw_authz, "COMMON_REPO_ROOT", shared_root)

    assert serverclaw_authz.repo_path("config/serverclaw-authz/bootstrap.json") == tracked_file


def test_cli_help_bootstraps_repo_platform_package_when_run_directly(tmp_path: Path) -> None:
    result = subprocess.run(
        ["uv", "run", "--with", "pyyaml", "python3", str(REPO_ROOT / "scripts" / "serverclaw_authz.py"), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
