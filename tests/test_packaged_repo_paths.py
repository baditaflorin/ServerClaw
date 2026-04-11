import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform import repo as repo_module
from platform.ledger import _common as ledger_common


def test_repo_path_uses_packaged_sibling_config_directory(monkeypatch, tmp_path: Path) -> None:
    service_root = tmp_path / "service"
    sibling_config = tmp_path / "config"
    service_root.mkdir()
    sibling_config.mkdir()

    config_path = sibling_config / "workflow-catalog.json"
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(repo_module, "REPO_ROOT", service_root)

    assert repo_module.repo_path("config", "workflow-catalog.json") == config_path
    assert repo_module.repo_path("inventory", "hosts.yml") == service_root / "inventory" / "hosts.yml"


def test_load_event_type_registry_reads_packaged_sibling_config(monkeypatch, tmp_path: Path) -> None:
    service_root = tmp_path / "service"
    sibling_config = tmp_path / "config"
    service_root.mkdir()
    sibling_config.mkdir()

    event_types_path = sibling_config / "ledger-event-types.yaml"
    event_types_path.write_text("- execution.completed\n- execution.failed\n", encoding="utf-8")

    monkeypatch.setattr(repo_module, "REPO_ROOT", service_root)

    assert ledger_common.load_event_type_registry(repo_module.repo_path("config", "ledger-event-types.yaml")) == [
        "execution.completed",
        "execution.failed",
    ]
