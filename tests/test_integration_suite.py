from __future__ import annotations

import json
from pathlib import Path

import integration_suite


def write_service_catalog(repo_root: Path, payload: dict) -> None:
    config_dir = repo_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "service-capability-catalog.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def test_resolve_targets_prefers_active_environment(monkeypatch, tmp_path: Path) -> None:
    write_service_catalog(
        tmp_path,
        {
            "services": [
                {
                    "id": "api_gateway",
                    "public_url": "https://api.lv3.org",
                    "environments": {
                        "production": {"status": "active", "url": "https://api.lv3.org"},
                        "staging": {"status": "active", "url": "https://api.staging.lv3.org"},
                    },
                },
                {
                    "id": "keycloak",
                    "public_url": "https://sso.lv3.org",
                    "environments": {
                        "production": {"status": "active", "url": "https://sso.lv3.org"},
                        "staging": {"status": "active", "url": "https://sso.staging.lv3.org"},
                    },
                },
                {
                    "id": "windmill",
                    "internal_url": "http://10.10.10.20:8005",
                    "environments": {
                        "production": {"status": "active", "url": "http://10.10.10.20:8005"}
                    },
                },
            ]
        },
    )
    monkeypatch.delenv("LV3_INTEGRATION_KEYCLOAK_URL", raising=False)
    monkeypatch.delenv("LV3_INTEGRATION_WINDMILL_URL", raising=False)
    monkeypatch.delenv("LV3_WINDMILL_BASE_URL", raising=False)

    targets = integration_suite.resolve_targets(tmp_path, "staging")

    assert targets.gateway_url == "https://api.staging.lv3.org"
    assert targets.keycloak_url == "https://sso.staging.lv3.org"
    assert targets.windmill_url is None


def test_resolve_targets_prefers_worker_windmill_base_url_override(monkeypatch, tmp_path: Path) -> None:
    write_service_catalog(
        tmp_path,
        {
            "services": [
                {
                    "id": "windmill",
                    "internal_url": "http://100.64.0.1:8005",
                    "environments": {
                        "production": {"status": "active", "url": "http://100.64.0.1:8005"}
                    },
                }
            ]
        },
    )
    monkeypatch.delenv("LV3_INTEGRATION_WINDMILL_URL", raising=False)
    monkeypatch.setenv("LV3_WINDMILL_BASE_URL", "http://127.0.0.1:8000")

    targets = integration_suite.resolve_targets(tmp_path, "production")

    assert targets.windmill_url == "http://127.0.0.1:8000"


def test_resolve_targets_prefers_worker_proc_windmill_base_url_override(monkeypatch, tmp_path: Path) -> None:
    write_service_catalog(
        tmp_path,
        {
            "services": [
                {
                    "id": "windmill",
                    "internal_url": "http://100.64.0.1:8005",
                    "environments": {
                        "production": {"status": "active", "url": "http://100.64.0.1:8005"}
                    },
                }
            ]
        },
    )
    monkeypatch.delenv("LV3_INTEGRATION_WINDMILL_URL", raising=False)
    monkeypatch.delenv("LV3_WINDMILL_BASE_URL", raising=False)
    monkeypatch.setattr(
        integration_suite,
        "proc_env_override",
        lambda *names, proc_environ_path=Path("/proc/1/environ"): "http://127.0.0.1:8000",
    )

    targets = integration_suite.resolve_targets(tmp_path, "production")

    assert targets.windmill_url == "http://127.0.0.1:8000"


def test_run_suite_records_skip_when_no_targets(monkeypatch, tmp_path: Path) -> None:
    write_service_catalog(tmp_path, {"services": []})
    report_file = tmp_path / ".local" / "integration-tests" / "gate.json"
    monkeypatch.delenv("LV3_INTEGRATION_WINDMILL_URL", raising=False)
    monkeypatch.delenv("LV3_WINDMILL_BASE_URL", raising=False)

    exit_code, payload = integration_suite.run_suite(
        repo_root=tmp_path,
        mode="gate",
        environment="staging",
        report_file=report_file,
    )

    assert exit_code == 0
    assert payload["status"] == "skipped"
    assert report_file.exists()


def test_run_suite_invokes_pytest_when_targets_exist(monkeypatch, tmp_path: Path) -> None:
    write_service_catalog(
        tmp_path,
        {
            "services": [
                {
                    "id": "keycloak",
                    "public_url": "https://sso.lv3.org",
                    "environments": {
                        "staging": {"status": "active", "url": "https://sso.staging.lv3.org"}
                    },
                }
            ]
        },
    )
    monkeypatch.delenv("LV3_INTEGRATION_WINDMILL_URL", raising=False)
    monkeypatch.delenv("LV3_WINDMILL_BASE_URL", raising=False)

    def fake_run_pytest(repo_root: Path, mode: str, extra_args: list[str], selection: list[str] | None = None):
        assert repo_root == tmp_path
        assert mode == "gate"
        assert extra_args == ["-q"]
        assert selection == ["tests/integration/test_authentication.py::test_keycloak_issues_valid_jwt"]
        reporter = integration_suite.SuiteReporter()
        reporter.results = {
            "tests/integration/test_authentication.py::test_keycloak_issues_valid_jwt": {
                "nodeid": "tests/integration/test_authentication.py::test_keycloak_issues_valid_jwt",
                "outcome": "passed",
                "duration_seconds": 0.12,
                "longrepr": "",
            }
        }
        return 0, reporter, 0.12

    monkeypatch.setattr(integration_suite, "run_pytest", fake_run_pytest)

    exit_code, payload = integration_suite.run_suite(
        repo_root=tmp_path,
        mode="gate",
        environment="staging",
        extra_args=["-q"],
        selection=["tests/integration/test_authentication.py::test_keycloak_issues_valid_jwt"],
        required_service_ids=["keycloak"],
    )

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["summary"]["passed"] == 1
    assert payload["selection"] == ["tests/integration/test_authentication.py::test_keycloak_issues_valid_jwt"]
    assert payload["required_service_ids"] == ["keycloak"]
