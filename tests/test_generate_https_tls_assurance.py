from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "generate_https_tls_assurance.py"


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configure_empty_runtime_outputs(module, tmp_path: Path) -> tuple[Path, Path]:
    targets = tmp_path / "file_sd" / "https_tls_targets.yml"
    alerts = tmp_path / "rules" / "https_tls_alerts.yml"
    module.PROMETHEUS_TARGETS_PATH = targets
    module.PROMETHEUS_ALERTS_PATH = alerts
    module.discover_https_tls_targets = lambda environment: []
    return targets, alerts


def write_current_targets(module, targets: Path) -> None:
    targets.parent.mkdir(parents=True)
    targets.write_text(module.build_targets_text_with_markers([]), encoding="utf-8")


def test_check_if_present_accepts_clean_checkout_with_tracked_targets_and_no_ignored_alert(tmp_path: Path) -> None:
    module = load_module("generate_https_tls_assurance_absent_runtime_outputs")
    targets, alerts = configure_empty_runtime_outputs(module, tmp_path)
    write_current_targets(module, targets)

    assert module.main(["--check-if-present"]) == 0
    assert targets.is_file()
    assert not alerts.exists()


def test_check_if_present_rejects_drift_when_any_runtime_output_exists(tmp_path: Path) -> None:
    module = load_module("generate_https_tls_assurance_present_runtime_outputs")
    targets, alerts = configure_empty_runtime_outputs(module, tmp_path)
    write_current_targets(module, targets)
    alerts.parent.mkdir(parents=True)
    alerts.write_text("stale generated content\n", encoding="utf-8")

    assert module.main(["--check-if-present"]) == 1
    assert targets.is_file()
    assert alerts.read_text(encoding="utf-8") == "stale generated content\n"
