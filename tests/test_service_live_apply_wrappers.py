import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_CAPABILITY_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"


def test_live_apply_wrappers_import_the_canonical_service_playbooks() -> None:
    wrappers = {
        "librechat": {
            "path": REPO_ROOT / "playbooks" / "services" / "librechat.yml",
            "playbook": "../librechat.yml",
        },
        "litellm": {
            "path": REPO_ROOT / "playbooks" / "services" / "litellm.yml",
            "playbook": "../litellm.yml",
        },
        "repowise": {
            "path": REPO_ROOT / "playbooks" / "services" / "repowise.yml",
            "playbook": "../repowise.yml",
        },
    }

    for _service, config in wrappers.items():
        wrapper_text = config["path"].read_text(encoding="utf-8")
        assert "# Purpose:" in wrapper_text
        assert yaml.safe_load(wrapper_text) == [{"import_playbook": config["playbook"]}]


def test_service_catalog_uses_wrapper_surfaces_for_live_apply_services() -> None:
    services = {
        entry["id"]: entry
        for entry in json.loads(SERVICE_CAPABILITY_CATALOG_PATH.read_text(encoding="utf-8"))["services"]
    }

    assert services["librechat"]["deployment_surface"] == "playbooks/services/librechat.yml"
    assert services["litellm"]["deployment_surface"] == "playbooks/services/litellm.yml"
    assert services["repowise"]["deployment_surface"] == "playbooks/services/repowise.yml"
