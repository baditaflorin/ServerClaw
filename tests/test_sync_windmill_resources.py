from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sync_windmill_resources as module


def test_sync_resource_types_uses_shared_admin_workspace(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_resource_type_exists(*, base_url: str, workspace: str, token: str, name: str, timeout_s: float) -> bool:
        calls.append({"kind": "exists", "workspace": workspace, "name": name})
        return False

    def fake_request_json_or_text(
        *,
        base_url: str,
        workspace: str,
        token: str,
        path: str,
        method: str,
        payload=None,
        expected_statuses: tuple[int, ...],
        timeout_s: float = module.DEFAULT_HTTP_TIMEOUT_S,
    ) -> tuple[int, str]:
        calls.append(
            {
                "kind": "request",
                "workspace": workspace,
                "path": path,
                "method": method,
                "payload": payload,
            }
        )
        return (201, "created")

    monkeypatch.setattr(module, "resource_type_exists", fake_resource_type_exists)
    monkeypatch.setattr(module, "request_json_or_text", fake_request_json_or_text)

    results = module.sync_resource_types(
        base_url="http://127.0.0.1:8000",
        resource_type_workspace="admins",
        token="token",
        resource_types=[{"name": "ntfy_platform_channel", "schema": {"type": "object"}, "description": "test"}],
        timeout_s=10.0,
    )

    assert results == [{"kind": "resource_type", "name": "ntfy_platform_channel", "status": "created"}]
    assert calls[0] == {"kind": "exists", "workspace": "admins", "name": "ntfy_platform_channel"}
    assert calls[1]["workspace"] == "admins"
    assert calls[1]["path"] == "resources/type/create"
    assert calls[1]["payload"]["workspace_id"] == "admins"
