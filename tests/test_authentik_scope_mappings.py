from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "reconcile_authentik_scope_mappings.py"
SCRIPT_DIR = SCRIPT_PATH.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("reconcile_authentik_scope_mappings", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeAPI:
    def __init__(self, mappings: list[dict[str, Any]] | None = None) -> None:
        self.mappings = list(mappings or [])
        self.posts: list[dict[str, Any]] = []
        self.patches: list[tuple[str, dict[str, Any]]] = []

    def list_all(self, path: str) -> list[dict[str, Any]]:
        assert path == MODULE.SCOPE_MAPPINGS_PATH
        return self.mappings

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert path == MODULE.SCOPE_MAPPINGS_PATH
        self.posts.append(dict(payload))
        created = {**payload, "expression": payload["expression"].rstrip(), "pk": 42}
        self.mappings.append(created)
        return created

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.patches.append((path, dict(payload)))
        mapping = next(row for row in self.mappings if path == f"{MODULE.SCOPE_MAPPINGS_PATH}{row['pk']}/")
        mapping.update(payload)
        return dict(mapping)


def load_manifest() -> dict[str, Any]:
    return MODULE.load_manifest(REPO_ROOT / "config" / "authentik" / "scope-mappings.yaml")


def test_manifest_is_grafana_scoped_and_minimizes_group_disclosure() -> None:
    manifest = load_manifest()
    mapping = manifest["mappings"][0]

    assert mapping["scope_name"] == "grafana-groups"
    assert MODULE.MANAGED_MARKER in mapping["description"].casefold()
    assert '"groups"' in mapping["expression"]
    assert '"grafana-admins", "grafana-viewers"' in mapping["expression"]
    assert "platform-admins" not in mapping["expression"]


def test_create_is_idempotent_and_does_not_echo_expression() -> None:
    api = FakeAPI()

    first = MODULE.reconcile_manifest(load_manifest(), api, apply=True)

    assert first["changed"] is True
    assert first["changes"] == [
        {
            "scope_name": "grafana-groups",
            "action": "create",
            "pk": None,
            "fields": sorted(MODULE.MANAGED_FIELDS),
        }
    ]
    assert first["mappings"] == [{"scope_name": "grafana-groups", "pk": 42, "action": "create"}]
    assert "request.user.ak_groups" not in str(first)
    assert len(api.posts) == 1
    assert api.posts[0]["scope_name"] == "grafana-groups"

    second = MODULE.reconcile_manifest(load_manifest(), api, apply=True)
    assert second["changed"] is False
    assert second["changes"] == []
    assert len(api.posts) == 1
    assert api.patches == []


def test_managed_drift_patches_only_the_changed_field() -> None:
    manifest = load_manifest()
    desired = manifest["mappings"][0]
    current = {
        "pk": 42,
        "name": desired["name"],
        "scope_name": desired["scope_name"],
        "description": desired["description"],
        "expression": "return {}",
    }
    api = FakeAPI([current])

    result = MODULE.reconcile_manifest(manifest, api, apply=True)

    assert result["changes"][0]["fields"] == ["expression"]
    assert api.patches == [(f"{MODULE.SCOPE_MAPPINGS_PATH}42/", {"expression": desired["expression"]})]


def test_unmanaged_scope_collision_is_rejected_without_mutation() -> None:
    api = FakeAPI(
        [
            {
                "pk": 42,
                "name": "Manually created Grafana scope",
                "scope_name": "grafana-groups",
                "description": "operator-defined",
                "expression": "return {}",
            }
        ]
    )

    with pytest.raises(MODULE.ReconcileError, match="not owned by this manifest"):
        MODULE.reconcile_manifest(load_manifest(), api, apply=True)

    assert api.posts == []
    assert api.patches == []


def test_unknown_selection_is_rejected_before_api_mutation() -> None:
    api = FakeAPI()

    with pytest.raises(MODULE.ReconcileError, match="Unknown scope mapping"):
        MODULE.reconcile_manifest(load_manifest(), api, apply=True, selected_mappings={"missing"})

    assert api.posts == []
    assert api.patches == []
