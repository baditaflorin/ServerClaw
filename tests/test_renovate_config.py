import importlib
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_renovate_module(monkeypatch: pytest.MonkeyPatch, root: Path):
    monkeypatch.chdir(root)
    import renovate_config

    renovate_config = importlib.reload(renovate_config)
    monkeypatch.setattr(renovate_config, "RENOVATE_CONFIG_PATH", root / "config" / "renovate.json")
    monkeypatch.setattr(
        renovate_config,
        "RENOVATE_CONFIG_SCHEMA_PATH",
        root / "docs" / "schema" / "renovate-config.schema.json",
    )
    return renovate_config


def test_repo_renovate_config_validates() -> None:
    import renovate_config

    config = renovate_config.load_renovate_config()
    renovate_config.validate_renovate_config(config)


def test_missing_patch_automerge_rule_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "docs" / "schema").mkdir(parents=True)
    payload = json.loads((REPO_ROOT / "config" / "renovate.json").read_text(encoding="utf-8"))
    payload["packageRules"][0]["automerge"] = False
    (tmp_path / "config" / "renovate.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "docs" / "schema" / "renovate-config.schema.json").write_text(
        (REPO_ROOT / "docs" / "schema" / "renovate-config.schema.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    renovate_config = load_renovate_module(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="patch/digest automerge rule"):
        renovate_config.validate_renovate_config(renovate_config.load_renovate_config())


def test_missing_image_catalog_manager_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "docs" / "schema").mkdir(parents=True)
    payload = json.loads((REPO_ROOT / "config" / "renovate.json").read_text(encoding="utf-8"))
    payload["customManagers"][0]["managerFilePatterns"] = ["/^config\\/different-file\\.json$/"]
    (tmp_path / "config" / "renovate.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "docs" / "schema" / "renovate-config.schema.json").write_text(
        (REPO_ROOT / "docs" / "schema" / "renovate-config.schema.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    renovate_config = load_renovate_module(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="regex manager for config/image-catalog.json"):
        renovate_config.validate_renovate_config(renovate_config.load_renovate_config())
