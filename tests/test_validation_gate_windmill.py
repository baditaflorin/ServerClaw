from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "gate-status.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_gate_status_wrapper_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_missing", WRAPPER_PATH)
    payload = module.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_gate_status_wrapper_reads_repo_status_payload(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_present", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "config").mkdir()
    (repo_root / "receipts" / "gate-bypasses").mkdir(parents=True)
    (repo_root / ".local" / "validation-gate").mkdir(parents=True)
    (repo_root / "scripts" / "gate_status.py").write_text(
        (
            "import json\n"
            "import sys\n"
            "payload = {\n"
            "    'manifest_path': sys.argv[sys.argv.index('--manifest') + 1],\n"
            "    'enabled_checks': [],\n"
            "    'last_run': {'status': 'passed'},\n"
            "    'post_merge_run': None,\n"
            "    'latest_bypass': None,\n"
            "}\n"
            "print(json.dumps(payload))\n"
        ),
        encoding="utf-8",
    )

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["gate_status"]["manifest_path"].endswith("config/validation-gate.json")
    assert payload["gate_status"]["last_run"] == {"status": "passed"}


def test_gate_status_wrapper_uses_absolute_repo_paths(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_absolute_paths", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "config").mkdir(parents=True)
    (repo_root / ".local" / "validation-gate").mkdir(parents=True)
    (repo_root / "receipts" / "gate-bypasses").mkdir(parents=True)
    (repo_root / "config" / "validation-gate.json").write_text("{}", encoding="utf-8")
    (repo_root / "scripts" / "gate_status.py").write_text(
        (
            "import json\n"
            "import sys\n"
            "print(json.dumps({'argv': sys.argv[1:]}))\n"
        ),
        encoding="utf-8",
    )

    payload = module.main(repo_path=str(repo_root))
    argv = payload["gate_status"]["argv"]

    assert payload["status"] == "ok"
    assert argv[argv.index("--manifest") + 1] == str(repo_root / "config" / "validation-gate.json")
    assert argv[argv.index("--last-run") + 1] == str(repo_root / ".local" / "validation-gate" / "last-run.json")
    assert argv[argv.index("--post-merge-run") + 1] == str(
        repo_root / ".local" / "validation-gate" / "post-merge-last-run.json"
    )
    assert argv[argv.index("--bypass-dir") + 1] == str(repo_root / "receipts" / "gate-bypasses")


def test_gate_status_wrapper_returns_structured_error_on_command_failure(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_command_failure", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "config").mkdir(parents=True)
    (repo_root / ".local" / "validation-gate").mkdir(parents=True)
    (repo_root / "receipts" / "gate-bypasses").mkdir(parents=True)
    (repo_root / "config" / "validation-gate.json").write_text("{}", encoding="utf-8")
    (repo_root / "scripts" / "gate_status.py").write_text(
        "import sys\n"
        "sys.stderr.write('boom\\n')\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "error"
    assert payload["returncode"] == 1
    assert payload["stderr"] == "boom"
