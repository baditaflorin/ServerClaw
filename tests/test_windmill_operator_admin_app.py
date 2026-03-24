from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windmill_defaults_seed_operator_admin_scripts_and_app() -> None:
    defaults = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml").read_text()
    )

    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    raw_app_paths = {entry["path"] for entry in defaults["windmill_seed_raw_apps"]}

    assert {
        "f/lv3/operator_onboard",
        "f/lv3/operator_offboard",
        "f/lv3/sync_operators",
        "f/lv3/quarterly_access_review",
        "f/lv3/operator_roster",
        "f/lv3/operator_inventory",
    }.issubset(script_paths)
    assert "f/lv3/operator_access_admin" in raw_app_paths


def test_operator_admin_raw_app_bundle_references_expected_backend_scripts() -> None:
    app_dir = REPO_ROOT / "config/windmill/apps/f/lv3/operator_access_admin.raw_app"
    app_config = yaml.safe_load((app_dir / "raw_app.yaml").read_text())
    package = json.loads((app_dir / "package.json").read_text())
    app_source = (app_dir / "App.tsx").read_text()

    assert app_config["summary"] == "LV3 operator access admin console"
    assert package["dependencies"]["react"] == "19.0.0"
    assert package["dependencies"]["windmill-client"] == "^1"
    assert "Operator Access Admin" in app_source
    assert "backend.create_operator" in app_source
    assert "backend.offboard_operator" in app_source
    assert "backend.sync_operators" in app_source
    assert "backend.operator_inventory" in app_source

    expected_backend_refs = {
        "list_operators.yaml": "f/lv3/operator_roster",
        "create_operator.yaml": "f/lv3/operator_onboard",
        "offboard_operator.yaml": "f/lv3/operator_offboard",
        "sync_operators.yaml": "f/lv3/sync_operators",
        "operator_inventory.yaml": "f/lv3/operator_inventory",
    }
    for file_name, expected_path in expected_backend_refs.items():
        payload = yaml.safe_load((app_dir / "backend" / file_name).read_text())
        assert payload["type"] == "script"
        assert payload["path"] == expected_path


def test_operator_roster_script_returns_sanitized_roster(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    roster_path = repo_root / "config" / "operators.yaml"
    roster_path.parent.mkdir(parents=True)
    roster_path.write_text(
        yaml.safe_dump(
            {
                "operators": [
                    {
                        "id": "alice-example",
                        "name": "Alice Example",
                        "email": "alice@example.com",
                        "role": "admin",
                        "status": "active",
                        "notes": "primary operator",
                        "keycloak": {
                            "username": "alice.example",
                            "realm_roles": ["platform-admin"],
                            "groups": ["lv3-platform-admins"],
                        },
                        "ssh": {"public_keys": [{"name": "bootstrap", "fingerprint": "SHA256:test"}]},
                        "tailscale": {"login_email": "alice@example.com"},
                        "audit": {"onboarded_at": "2026-03-24T12:00:00Z"},
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    module = load_module(REPO_ROOT / "config/windmill/scripts/operator-roster.py", "operator_roster")
    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["operator_count"] == 1
    assert payload["active_count"] == 1
    assert payload["inactive_count"] == 0
    assert payload["operators"][0]["keycloak_username"] == "alice.example"
    assert payload["operators"][0]["ssh_enabled"] is True
    assert "public_keys" not in payload["operators"][0]


def test_operator_inventory_script_requires_operator_id() -> None:
    module = load_module(REPO_ROOT / "config/windmill/scripts/operator-inventory.py", "operator_inventory")
    payload = module.main(operator_id="")

    assert payload["status"] == "blocked"
    assert payload["reason"] == "operator_id is required"


def test_windmill_runtime_tasks_sync_raw_apps_via_wmill_cli() -> None:
    tasks = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml"
    ).read_text()

    assert "Sync repo-managed Windmill raw apps" in tasks
    assert "wmill sync push" in tasks
    assert "--skip-branch-validation" in tasks
    assert "WM_TOKEN" in tasks
