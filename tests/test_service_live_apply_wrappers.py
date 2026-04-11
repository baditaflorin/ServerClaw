import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_CAPABILITY_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"


def test_live_apply_wrappers_import_the_canonical_service_playbooks() -> None:
    wrappers = {
        "librechat": {
            "path": REPO_ROOT / "playbooks" / "services" / "librechat.yml",
            "purpose": "# Purpose: Provide the stable live-apply service wrapper for LibreChat.",
        },
        "litellm": {
            "path": REPO_ROOT / "playbooks" / "services" / "litellm.yml",
            "purpose": "# Purpose: Provide the stable live-apply service wrapper for LiteLLM.",
        },
        "repowise": {
            "path": REPO_ROOT / "playbooks" / "services" / "repowise.yml",
            "purpose": "# Purpose: Provide the stable live-apply service wrapper for Repowise.",
        },
    }

    for service, config in wrappers.items():
        wrapper_text = config["path"].read_text(encoding="utf-8")
        assert config["purpose"] in wrapper_text
        assert yaml.safe_load(wrapper_text) == [{"import_playbook": f"../{service}.yml"}]


def test_service_catalog_uses_wrapper_surfaces_for_live_apply_services() -> None:
    services = {
        entry["id"]: entry
        for entry in json.loads(SERVICE_CAPABILITY_CATALOG_PATH.read_text(encoding="utf-8"))["services"]
    }

    assert services["librechat"]["deployment_surface"] == "playbooks/services/librechat.yml"
    assert services["litellm"]["deployment_surface"] == "playbooks/services/litellm.yml"
    assert services["repowise"]["deployment_surface"] == "playbooks/services/repowise.yml"
