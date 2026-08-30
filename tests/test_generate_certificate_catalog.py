from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_certificate_catalog  # noqa: E402
import identity_yaml  # noqa: E402


def test_load_deployment_config_prefers_explicit_identity_overlay(tmp_path: Path) -> None:
    tracked_identity = tmp_path / "inventory" / "group_vars" / "all" / "identity.yml"
    tracked_identity.parent.mkdir(parents=True)
    tracked_identity.write_text("platform_domain: example.com\n", encoding="utf-8")

    selected_identity = tmp_path / "identity.yml.0mcp"
    selected_identity.write_text("platform_domain: example.org\n", encoding="utf-8")

    with (
        patch.dict("os.environ", {"PLATFORM_IDENTITY_OVERLAY": str(selected_identity)}, clear=False),
        patch.object(identity_yaml, "_find_identity_path", return_value=tracked_identity),
    ):
        config = generate_certificate_catalog.load_deployment_config()

    assert config["platform_domain"] == "example.org"


def test_substitute_domain_derives_certificate_lineage_from_domain() -> None:
    payload = {
        "endpoint": "id.example.com",
        "bundle_path": "/etc/letsencrypt/live/{{ platform_config_prefix }}-edge/fullchain.pem",
    }

    assert generate_certificate_catalog.substitute_domain(payload, "example.org") == {
        "endpoint": "id.example.org",
        "bundle_path": "/etc/letsencrypt/live/0mcp-edge/fullchain.pem",
    }
