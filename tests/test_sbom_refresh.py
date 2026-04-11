from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "sbom_refresh.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sbom_refresh = _load_module(SCRIPT_PATH, "sbom_refresh")


def test_build_ntfy_publish_command_uses_governed_registry_defaults(monkeypatch) -> None:
    monkeypatch.delenv("LV3_NTFY_BASE_URL", raising=False)
    monkeypatch.delenv("LV3_NTFY_PUBLISHER", raising=False)
    monkeypatch.delenv("LV3_NTFY_TOPIC", raising=False)

    command = sbom_refresh.build_ntfy_publish_command(
        config={
            "ntfy": {"base_url": "http://10.10.10.20:2586", "publisher": "windmill", "topic": "platform-security-warn"}
        },
        message="delta detected",
    )

    assert command[0] == sys.executable
    assert "--publisher" in command
    assert command[command.index("--publisher") + 1] == "windmill"
    assert "--topic" in command
    assert command[command.index("--topic") + 1] == "platform-security-warn"
    assert "--base-url" in command
    assert command[command.index("--base-url") + 1] == "http://10.10.10.20:2586"
