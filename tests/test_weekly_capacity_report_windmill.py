from __future__ import annotations

import importlib.util
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
