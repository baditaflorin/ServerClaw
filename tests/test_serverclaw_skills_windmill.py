from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "serverclaw-skills.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_wrapper_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    module = load_module("serverclaw_skills_windmill_missing", WRAPPER_PATH)
    payload = module.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_wrapper_loads_repo_managed_skill_resolver() -> None:
    module = load_module("serverclaw_skills_windmill_live", WRAPPER_PATH)

    payload = module.main(repo_path=str(REPO_ROOT), workspace_id="ops", include_prompt_manifest=True)

    assert payload["status"] == "ok"
    assert payload["result"]["workspace_id"] == "ops"
    active = {entry["skill_id"]: entry for entry in payload["result"]["active_skills"]}
    assert active["platform-observe"]["source_tier"] == "workspace"
