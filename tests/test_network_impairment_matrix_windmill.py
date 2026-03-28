from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "network-impairment-matrix.py"
SPEC = importlib.util.spec_from_file_location("network_impairment_matrix_windmill", SCRIPT_PATH)
network_impairment_matrix_windmill = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(network_impairment_matrix_windmill)


def test_main_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    payload = network_impairment_matrix_windmill.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_main_executes_network_impairment_matrix_script(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "network_impairment_matrix.py").write_text(
        "def main(**kwargs):\n"
        "    return {'status': 'planned', 'entry_count': 4, 'kwargs': kwargs}\n",
        encoding="utf-8",
    )

    payload = network_impairment_matrix_windmill.main(
        repo_path=str(repo_root),
        target_class="staging",
    )

    assert payload["status"] == "planned"
    assert payload["entry_count"] == 4
    assert payload["kwargs"]["output_format"] == "json"

def test_main_falls_back_to_uv_when_yaml_is_missing(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "network_impairment_matrix.py").write_text("def main(**kwargs):\n    return kwargs\n", encoding="utf-8")

    class Result:
        returncode = 0
        stdout = json.dumps({"status": "planned", "entry_count": 4})
        stderr = ""

    def raise_missing_yaml(_repo_root: Path):
        raise ModuleNotFoundError("No module named 'yaml'", name="yaml")

    monkeypatch.setattr(network_impairment_matrix_windmill, "_load_repo_script", raise_missing_yaml)
    monkeypatch.setattr(network_impairment_matrix_windmill.subprocess, "run", lambda *args, **kwargs: Result())

    payload = network_impairment_matrix_windmill.main(repo_path=str(repo_root), target_class="staging")
    assert payload["status"] == "planned"
    assert payload["entry_count"] == 4


def test_main_falls_back_to_uv_when_repo_script_reports_missing_pyyaml(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "network_impairment_matrix.py").write_text("def main(**kwargs):\n    raise RuntimeError('PyYAML is required to load the network impairment matrix')\n", encoding="utf-8")

    class Result:
        returncode = 0
        stdout = json.dumps({"status": "planned", "entry_count": 4})
        stderr = ""

    monkeypatch.setattr(network_impairment_matrix_windmill.subprocess, "run", lambda *args, **kwargs: Result())

    payload = network_impairment_matrix_windmill.main(repo_path=str(repo_root), target_class="staging")
    assert payload["status"] == "planned"
    assert payload["entry_count"] == 4
