from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "weekly-capacity-report.py"


def load_module():
    spec = importlib.util.spec_from_file_location("weekly_capacity_report", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_weekly_capacity_report_imports_from_fresh_checkout() -> None:
    module = load_module()

    blocked = module.main(repo_path="/tmp/weekly-capacity-report-missing", no_live_metrics=True)

    assert blocked["status"] == "blocked"
    assert "missing capacity model" in blocked["reason"]


def test_weekly_capacity_report_loads_capacity_helpers_from_repo_path(tmp_path: Path) -> None:
    module = load_module()
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "config" / "capacity-model.json").write_text('{"schema_version":"1.0.0"}\n', encoding="utf-8")
    (tmp_path / "scripts" / "capacity_report.py").write_text(
        "class Report:\n"
        "    metrics_source = 'repo-only'\n"
        "def load_capacity_model(path):\n"
        "    return {'path': str(path)}\n"
        "def build_report(model, with_live_metrics):\n"
        "    return Report()\n"
        "def render_markdown(report):\n"
        "    return '# capacity\\n'\n",
        encoding="utf-8",
    )
    sys.modules.pop("capacity_report", None)

    payload = module.main(repo_path=str(tmp_path), no_live_metrics=True)

    assert payload["status"] == "ok"
    assert payload["metrics_source"] == "repo-only"
    assert payload["markdown"] == "# capacity\n"


def test_weekly_capacity_report_falls_back_to_uv_when_pyyaml_is_missing(monkeypatch, tmp_path: Path) -> None:
    module = load_module()
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "config" / "capacity-model.json").write_text('{"schema_version":"1.0.0"}\n', encoding="utf-8")

    class CapacityReportModule:
        @staticmethod
        def load_capacity_model(path: Path) -> dict[str, str]:
            raise RuntimeError("Missing dependency: PyYAML. Run via 'uv run --with pyyaml ...'.")

    monkeypatch.setattr(module, "_load_capacity_report", lambda repo_root: CapacityReportModule())

    def fake_run(command, *, input, text, capture_output, check, cwd):
        assert command[:5] == ["uv", "run", "--with", "pyyaml", "python"]
        assert str(tmp_path) in command
        assert cwd == tmp_path
        assert "capacity_report.render_markdown" in input
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"metrics_source":"disabled","markdown":"# capacity\\n"}\n',
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(repo_path=str(tmp_path), no_live_metrics=True)

    assert payload["status"] == "ok"
    assert payload["metrics_source"] == "disabled"
    assert payload["markdown"] == "# capacity\n"
