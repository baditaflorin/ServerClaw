from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any, cast


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "atlas-drift-check.py"


def load_module(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, WRAPPER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wrapper_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    module = load_module("atlas_drift_missing")
    payload = cast(dict[str, Any], module.main(repo_path=str(tmp_path / "missing")))

    assert payload["status"] == "blocked"


def test_wrapper_executes_repo_script_and_parses_clean_json(monkeypatch, tmp_path: Path) -> None:
    module = load_module("atlas_drift_present")
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "atlas_schema.py").write_text("# placeholder\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").chmod(0o755)
    captured: dict[str, Any] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"status": "clean", "drift_count": 0}),
            "",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = cast(dict[str, Any], module.main(repo_path=str(repo_root)))

    assert payload["status"] == "ok"
    assert captured["cwd"] == repo_root
    assert captured["command"][1:4] == ["docker", "nats-py", "pyyaml"]
    assert captured["env"]["LV3_ATLAS_FORCE_DIRECT_ENDPOINTS"] == "1"
    assert captured["env"]["LV3_NATS_URL"] == "nats://127.0.0.1:4222"
    assert "scripts/atlas_schema.py" in captured["command"]
    assert payload["report"] == {"status": "clean", "drift_count": 0}


def test_wrapper_overrides_blank_direct_endpoint_env_values(monkeypatch, tmp_path: Path) -> None:
    module = load_module("atlas_drift_blank_env")
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "atlas_schema.py").write_text("# placeholder\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").chmod(0o755)
    captured: dict[str, Any] = {}

    def fake_run(command, **kwargs):
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"status": "clean", "drift_count": 0}),
            "",
        )

    monkeypatch.setenv("LV3_ATLAS_FORCE_DIRECT_ENDPOINTS", "")
    monkeypatch.setenv("LV3_NATS_URL", "   ")
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = cast(dict[str, Any], module.main(repo_path=str(repo_root)))

    assert payload["status"] == "ok"
    assert captured["env"]["LV3_ATLAS_FORCE_DIRECT_ENDPOINTS"] == "1"
    assert captured["env"]["LV3_NATS_URL"] == "nats://127.0.0.1:4222"


def test_wrapper_loads_worker_secret_files_when_runtime_env_is_missing(monkeypatch, tmp_path: Path) -> None:
    module = load_module("atlas_drift_worker_secret_files")
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / ".local" / "openbao").mkdir(parents=True)
    (repo_root / ".local" / "ntfy").mkdir(parents=True)
    (repo_root / "scripts" / "atlas_schema.py").write_text("# placeholder\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").chmod(0o755)
    (repo_root / ".local" / "openbao" / "init.json").write_text(
        json.dumps({"keys_base64": ["key-one"], "root_token": "root-token"}),
        encoding="utf-8",
    )
    (repo_root / ".local" / "openbao" / "atlas-approle.json").write_text(
        json.dumps({"role_id": "atlas-role", "secret_id": "atlas-secret"}),
        encoding="utf-8",
    )
    (repo_root / ".local" / "ntfy" / "alertmanager-password.txt").write_text(
        "ntfy-password\n",
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def fake_run(command, **kwargs):
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"status": "clean", "drift_count": 0}),
            "",
        )

    monkeypatch.delenv("LV3_ATLAS_OPENBAO_APPROLE_JSON", raising=False)
    monkeypatch.delenv("LV3_ATLAS_OPENBAO_INIT_JSON", raising=False)
    monkeypatch.delenv("LV3_NTFY_ALERTMANAGER_PASSWORD", raising=False)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = cast(dict[str, Any], module.main(repo_path=str(repo_root)))

    assert payload["status"] == "ok"
    assert json.loads(captured["env"]["LV3_ATLAS_OPENBAO_APPROLE_JSON"]) == {
        "role_id": "atlas-role",
        "secret_id": "atlas-secret",
    }
    assert json.loads(captured["env"]["LV3_ATLAS_OPENBAO_INIT_JSON"]) == {
        "keys_base64": ["key-one"],
        "root_token": "root-token",
    }
    assert captured["env"]["LV3_NTFY_ALERTMANAGER_PASSWORD"] == "ntfy-password"


def test_wrapper_prefers_seed_job_secret_files_when_repo_local_worker_secrets_are_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    module = load_module("atlas_drift_seed_job_secret_files")
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / ".local" / "windmill-job-secrets" / "openbao").mkdir(parents=True)
    (repo_root / ".local" / "windmill-job-secrets" / "ntfy").mkdir(parents=True)
    (repo_root / "scripts" / "atlas_schema.py").write_text("# placeholder\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").chmod(0o755)
    (repo_root / ".local" / "windmill-job-secrets" / "openbao" / "init.json").write_text(
        json.dumps({"keys_base64": ["key-one"], "root_token": "root-token"}),
        encoding="utf-8",
    )
    (repo_root / ".local" / "windmill-job-secrets" / "openbao" / "atlas-approle.json").write_text(
        json.dumps({"role_id": "atlas-role", "secret_id": "atlas-secret"}),
        encoding="utf-8",
    )
    (repo_root / ".local" / "windmill-job-secrets" / "ntfy" / "alertmanager-password.txt").write_text(
        "ntfy-password\n",
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def fake_run(command, **kwargs):
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"status": "clean", "drift_count": 0}),
            "",
        )

    monkeypatch.delenv("LV3_ATLAS_OPENBAO_APPROLE_JSON", raising=False)
    monkeypatch.delenv("LV3_ATLAS_OPENBAO_INIT_JSON", raising=False)
    monkeypatch.delenv("LV3_NTFY_ALERTMANAGER_PASSWORD", raising=False)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = cast(dict[str, Any], module.main(repo_path=str(repo_root)))

    assert payload["status"] == "ok"
    assert json.loads(captured["env"]["LV3_ATLAS_OPENBAO_APPROLE_JSON"]) == {
        "role_id": "atlas-role",
        "secret_id": "atlas-secret",
    }
    assert json.loads(captured["env"]["LV3_ATLAS_OPENBAO_INIT_JSON"]) == {
        "keys_base64": ["key-one"],
        "root_token": "root-token",
    }
    assert captured["env"]["LV3_NTFY_ALERTMANAGER_PASSWORD"] == "ntfy-password"


def test_wrapper_loads_worker_secrets_from_proc_env_when_files_are_unreadable(monkeypatch, tmp_path: Path) -> None:
    module = load_module("atlas_drift_proc_env")
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / ".local" / "openbao").mkdir(parents=True)
    (repo_root / ".local" / "ntfy").mkdir(parents=True)
    (repo_root / "scripts" / "atlas_schema.py").write_text("# placeholder\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").chmod(0o755)
    captured: dict[str, Any] = {}

    def fake_run(command, **kwargs):
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"status": "clean", "drift_count": 0}),
            "",
        )

    def fake_read_proc_env_var(name: str, proc_environ_path: Path = Path("/proc/1/environ")) -> str:
        values = {
            "LV3_ATLAS_OPENBAO_APPROLE_JSON": json.dumps({"role_id": "atlas-role", "secret_id": "atlas-secret"}),
            "LV3_ATLAS_OPENBAO_INIT_JSON": json.dumps({"keys_base64": ["key-one"], "root_token": "root-token"}),
            "LV3_NTFY_ALERTMANAGER_PASSWORD": "ntfy-password",
        }
        return values.get(name, "")

    monkeypatch.delenv("LV3_ATLAS_OPENBAO_APPROLE_JSON", raising=False)
    monkeypatch.delenv("LV3_ATLAS_OPENBAO_INIT_JSON", raising=False)
    monkeypatch.delenv("LV3_NTFY_ALERTMANAGER_PASSWORD", raising=False)
    monkeypatch.setattr(module, "read_proc_env_var", fake_read_proc_env_var)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = cast(dict[str, Any], module.main(repo_path=str(repo_root)))

    assert payload["status"] == "ok"
    assert json.loads(captured["env"]["LV3_ATLAS_OPENBAO_APPROLE_JSON"]) == {
        "role_id": "atlas-role",
        "secret_id": "atlas-secret",
    }
    assert json.loads(captured["env"]["LV3_ATLAS_OPENBAO_INIT_JSON"]) == {
        "keys_base64": ["key-one"],
        "root_token": "root-token",
    }
    assert captured["env"]["LV3_NTFY_ALERTMANAGER_PASSWORD"] == "ntfy-password"


def test_wrapper_surfaces_drift_without_treating_it_as_runner_error(monkeypatch, tmp_path: Path) -> None:
    module = load_module("atlas_drift_detected")
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "atlas_schema.py").write_text("# placeholder\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").chmod(0o755)

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            2,
            json.dumps({"status": "drift_detected", "drift_count": 2}),
            "",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = cast(dict[str, Any], module.main(repo_path=str(repo_root)))

    assert payload["status"] == "drift"
    assert payload["report"]["drift_count"] == 2


def test_wrapper_treats_exit_code_two_without_structured_drift_report_as_error(monkeypatch, tmp_path: Path) -> None:
    module = load_module("atlas_drift_runner_error")
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "atlas_schema.py").write_text("# placeholder\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").chmod(0o755)

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            2,
            "",
            "Atlas schema automation error: permission denied",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = cast(dict[str, Any], module.main(repo_path=str(repo_root)))

    assert payload["status"] == "error"
    assert payload["stderr"] == "Atlas schema automation error: permission denied"
