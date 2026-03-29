from __future__ import annotations

import importlib.util
import json
import subprocess
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


def write_health_probe_catalog(repo_root: Path, windmill_probe_url: str = "http://127.0.0.1:8000/api/version") -> None:
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "health-probe-catalog.json").write_text(
        json.dumps(
            {
                "services": {
                    "windmill": {
                        "liveness": {
                            "url": windmill_probe_url,
                        }
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_stage_smoke_wrapper_exports_worker_local_windmill_url(monkeypatch, tmp_path: Path) -> None:
    write_health_probe_catalog(tmp_path)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts" / "stage_smoke_suites.py").write_text("# placeholder\n", encoding="utf-8")

    wrapper = load_module("windmill_stage_smoke_wrapper", "config/windmill/scripts/stage-smoke-suites.py")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, '{"status":"passed"}', "")

    monkeypatch.setattr(wrapper.subprocess, "run", fake_run)

    payload = wrapper.main(repo_path=str(tmp_path))

    assert payload["status"] == "ok"
    assert captured["cwd"] == tmp_path
    assert captured["env"]["LV3_INTEGRATION_WINDMILL_URL"] == "http://127.0.0.1:8000"
    assert captured["command"] == [
        "python3",
        str(tmp_path / "scripts" / "stage_smoke_suites.py"),
        "--service",
        "windmill",
        "--environment",
        "production",
    ]


def test_nightly_wrapper_sets_worker_local_windmill_url_before_run_suite(monkeypatch, tmp_path: Path) -> None:
    write_health_probe_catalog(tmp_path)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts" / "environment_catalog.py").write_text(
        "def environment_choices():\n    return ['production']\n\n"
        "def primary_environment():\n    return 'production'\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts" / "integration_suite.py").write_text(
        "import os\n\n"
        "def run_suite(**kwargs):\n"
        "    return 0, {\n"
        "        'status': 'passed',\n"
        "        'mode': kwargs['mode'],\n"
        "        'environment': kwargs['environment'],\n"
        "        'summary': {'passed': 1, 'failed': 0, 'skipped': 0, 'total': 1},\n"
        "        'tests': [],\n"
        "        'duration_seconds': 0.0,\n"
        "        'windmill_url': os.environ.get('LV3_INTEGRATION_WINDMILL_URL'),\n"
        "    }\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("LV3_INTEGRATION_WINDMILL_URL", raising=False)
    sys.modules.pop("environment_catalog", None)
    sys.modules.pop("integration_suite", None)

    wrapper = load_module("windmill_nightly_wrapper", "config/windmill/scripts/nightly-integration-tests.py")

    payload = wrapper.main(repo_path=str(tmp_path), environment="production")

    assert payload["status"] == "passed"
    assert payload["windmill_url"] == "http://127.0.0.1:8000"
