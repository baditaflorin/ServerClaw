from __future__ import annotations

import json
from pathlib import Path

import serverclaw_authz


REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = REPO_ROOT / "config" / "serverclaw-authz" / "bootstrap.json"
MODEL_PATH = REPO_ROOT / "config" / "serverclaw-authz" / "model.json"


def test_bootstrap_config_points_to_stable_repo_managed_principals() -> None:
    config = json.loads(BOOTSTRAP_PATH.read_text(encoding="utf-8"))

    assert config["store"]["name"] == "serverclaw-authz"
    assert config["principals"]["operator"]["principal"] == "principal:keycloak-user:florin.badita"
    assert config["principals"]["runtime"]["principal"] == "principal:keycloak-client:serverclaw-runtime"
    assert any(item["name"] == "unauthorized-client-cannot-read-data-scope" for item in config["checks"])


def test_model_covers_workspace_assistant_skill_connector_scope_and_channel() -> None:
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    type_names = {item["type"] for item in model["type_definitions"]}

    assert type_names == {"principal", "workspace", "assistant", "skill", "connector", "data_scope", "channel"}
    channel = next(item for item in model["type_definitions"] if item["type"] == "channel")
    assert "can_send" in channel["relations"]
    assert "can_receive" in channel["relations"]


def test_normalize_model_payload_strips_runtime_only_fields() -> None:
    payload = {
        "id": "ignored",
        "schema_version": "1.1",
        "type_definitions": [
            {
                "type": "user",
                "relations": {},
                "metadata": {
                    "relations": {
                        "reader": {
                            "directly_related_user_types": [{"type": "principal", "condition": ""}],
                            "module": "",
                            "source_info": None,
                        }
                    },
                    "module": "",
                    "source_info": None,
                },
            }
        ],
        "conditions": {},
    }

    normalized = serverclaw_authz.normalize_model_payload(payload)

    assert "id" not in normalized
    assert normalized["type_definitions"][0]["metadata"]["relations"]["reader"]["directly_related_user_types"] == [
        {"type": "principal"}
    ]


def test_build_report_marks_failed_checks() -> None:
    config = json.loads(BOOTSTRAP_PATH.read_text(encoding="utf-8"))
    report = serverclaw_authz.build_report(
        config,
        mode="verify",
        openfga_url="http://100.64.0.1:8014",
        store_id="store-id",
        store_created=False,
        model_id="model-id",
        model_changed=False,
        principal_reports=[],
        check_results=[{"name": "demo", "passed": False}],
    )

    assert report["changed"] is False
    assert report["verification_passed"] is False
