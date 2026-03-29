from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeCompletedProcess:
    def __init__(self, *, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_runner_image_pull_failed_detects_registry_runner_errors() -> None:
    module = load_module("post_merge_gate", "config/windmill/scripts/post-merge-gate.py")

    assert module._runner_image_pull_failed(
        "",
        "docker: Error response from daemon: unsupported manifest media type and no default available: text/html",
    )
    assert module._runner_image_pull_failed(
        "Unable to find image 'registry.lv3.org/check-runner/python:3.12.10' locally",
        "",
    )
    assert not module._runner_image_pull_failed("normal stdout", "normal stderr")


def test_gate_status_runner_startup_failed_detects_docker_125_checks() -> None:
    module = load_module("post_merge_gate_status_detection", "config/windmill/scripts/post-merge-gate.py")

    assert module._gate_status_runner_startup_failed(
        {
            "status": "failed",
            "checks": [
                {"id": "schema-validation", "returncode": 125},
                {"id": "generated-docs", "returncode": 125},
            ],
        }
    )
    assert not module._gate_status_runner_startup_failed(
        {
            "status": "passed",
            "checks": [{"id": "schema-validation", "returncode": 0}],
        }
    )
    assert not module._gate_status_runner_startup_failed(
        {
            "status": "failed",
            "checks": [{"id": "schema-validation", "returncode": 1}],
        }
    )


def test_post_merge_gate_falls_back_to_validate_repo_when_runner_images_fail(tmp_path: Path, monkeypatch) -> None:
    module = load_module("post_merge_gate_fallback", "config/windmill/scripts/post-merge-gate.py")
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "config" / "windmill" / "scripts").mkdir(parents=True)
    (repo_root / "config").mkdir(exist_ok=True)
    (repo_root / "scripts" / "run_gate.py").write_text("print('stub')\n", encoding="utf-8")
    (repo_root / "config" / "validation-gate.json").write_text("{}", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(command, *, cwd):
        calls.append(command)
        if len(command) > 1 and command[0] == "python3" and command[1].endswith("run_gate.py"):
            return FakeCompletedProcess(
                returncode=1,
                stdout="Unable to find image 'registry.lv3.org/check-runner/python:3.12.10' locally",
                stderr="docker: Error response from daemon: unsupported manifest media type and no default available: text/html",
            )
        return FakeCompletedProcess(returncode=0, stdout="fallback ok", stderr="")

    monkeypatch.setattr(module, "_run", fake_run)

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["fallback_used"] is True
    assert payload["returncode"] == 0
    assert "primary_gate_error" in payload
    assert calls[0][0] == "python3"
    assert calls[1][:3] == ["git", "-C", str(repo_root)]
    assert calls[2] == [
        "./scripts/validate_repo.sh",
        "generated-vars",
        "role-argument-specs",
        "json",
        "alert-rules",
        "generated-docs",
        "generated-portals",
    ]
    assert calls[3][:3] == ["uv", "run", "--with"]
    assert calls[3][-2:] == ["scripts/provider_boundary_catalog.py", "--validate"]
    assert len(payload["commands"]) == 2

    status_path = repo_root / ".local" / "validation-gate" / "post-merge-last-run.json"
    status_payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert status_payload["status"] == "passed"
    assert status_payload["source"] == "windmill-post-merge-local-fallback"
    assert status_payload["checks"][0]["commands"][1]["command"].endswith(
        "scripts/provider_boundary_catalog.py --validate"
    )


def test_post_merge_gate_keeps_git_dependent_checks_when_git_checkout_exists(tmp_path: Path, monkeypatch) -> None:
    module = load_module("post_merge_gate_git_checkout", "config/windmill/scripts/post-merge-gate.py")
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "config").mkdir(parents=True)
    (repo_root / "scripts" / "run_gate.py").write_text("print('stub')\n", encoding="utf-8")
    (repo_root / "config" / "validation-gate.json").write_text("{}", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(command, *, cwd):
        calls.append(command)
        if command[:4] == ["git", "-C", str(repo_root), "rev-parse"]:
            return FakeCompletedProcess(returncode=0, stdout="true\n", stderr="")
        if len(command) > 1 and command[0] == "python3" and command[1].endswith("run_gate.py"):
            return FakeCompletedProcess(
                returncode=1,
                stdout="Unable to find image 'registry.lv3.org/check-runner/python:3.12.10' locally",
                stderr="docker: Error response from daemon: unsupported manifest media type and no default available: text/html",
            )
        return FakeCompletedProcess(returncode=0, stdout="fallback ok", stderr="")

    monkeypatch.setattr(module, "_run", fake_run)

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["fallback_used"] is True
    assert calls[1][:3] == ["git", "-C", str(repo_root)]
    assert calls[2] == [
        "./scripts/validate_repo.sh",
        "workstream-surfaces",
        "agent-standards",
        "generated-vars",
        "role-argument-specs",
        "json",
        "alert-rules",
        "generated-docs",
        "generated-portals",
    ]


def test_post_merge_gate_falls_back_when_gate_status_reports_runner_startup_failure(
    tmp_path: Path, monkeypatch
) -> None:
    module = load_module("post_merge_gate_status_fallback", "config/windmill/scripts/post-merge-gate.py")
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "config").mkdir(parents=True)
    (repo_root / "scripts" / "run_gate.py").write_text("print('stub')\n", encoding="utf-8")
    (repo_root / "config" / "validation-gate.json").write_text("{}", encoding="utf-8")

    status_path = repo_root / ".local" / "validation-gate" / "post-merge-last-run.json"
    calls: list[list[str]] = []

    def fake_run(command, *, cwd):
        calls.append(command)
        if len(command) > 1 and command[0] == "python3" and command[1].endswith("run_gate.py"):
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "checks": [
                            {"id": "schema-validation", "returncode": 125},
                            {"id": "generated-docs", "returncode": 125},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            return FakeCompletedProcess(returncode=0, stdout="{}", stderr="")
        return FakeCompletedProcess(returncode=0, stdout="fallback ok", stderr="")

    monkeypatch.setattr(module, "_run", fake_run)

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["fallback_used"] is True
    assert payload["primary_gate_error"]["returncode"] == 0
    assert calls[1][:3] == ["git", "-C", str(repo_root)]
    assert calls[2] == [
        "./scripts/validate_repo.sh",
        "generated-vars",
        "role-argument-specs",
        "json",
        "alert-rules",
        "generated-docs",
        "generated-portals",
    ]
