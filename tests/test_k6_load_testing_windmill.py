from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "k6-load-testing.py"


def load_module():
    spec = importlib.util.spec_from_file_location("k6_load_testing_windmill", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_k6_load_testing_blocks_when_repo_checkout_is_missing() -> None:
    module = load_module()

    blocked = module.main(repo_path="/tmp/k6-load-testing-missing")

    assert blocked["status"] == "blocked"
    assert "missing k6 runner" in blocked["reason"]


def test_k6_load_testing_invokes_repo_runner_via_uv(monkeypatch, tmp_path: Path) -> None:
    module = load_module()
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "scripts" / "k6_load_testing.py").write_text("# runner placeholder\n", encoding="utf-8")

    def fake_run(command, *, cwd, text, capture_output, check):
        assert command[:7] == ["uv", "run", "--with", "pyyaml", "--with", "nats-py", "python"]
        assert cwd == tmp_path
        assert "--publish-nats" in command
        assert "--notify-ntfy" in command
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"receipts": ["receipts/k6/load-keycloak.json"]}),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(
        repo_path=str(tmp_path),
        scenario="load",
        service="keycloak",
        publish_nats=True,
        notify_ntfy=True,
    )

    assert payload["status"] == "ok"
    assert payload["receipts"] == ["receipts/k6/load-keycloak.json"]
