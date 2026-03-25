from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import session_workspace


def test_resolve_session_workspace_uses_explicit_session_id(tmp_path: Path) -> None:
    workspace = session_workspace.resolve_session_workspace(
        repo_root=tmp_path,
        remote_workspace_base=Path("/srv/builds/repo"),
        session_id="ADR 0156 / test",
    )

    assert workspace.session_id == "ADR 0156 / test"
    assert workspace.session_slug == "adr-0156-test"
    assert workspace.local_state_root.endswith(".local/session-workspaces/adr-0156-test")
    assert workspace.remote_workspace_root == "/srv/builds/repo/.lv3-session-workspaces/adr-0156-test/repo"
    assert workspace.nats_prefix == "platform.ws.adr-0156-test"
    assert workspace.state_namespace == "ws:adr-0156-test"


def test_shell_output_contains_exportable_session_fields(tmp_path: Path) -> None:
    workspace = session_workspace.resolve_session_workspace(
        repo_root=tmp_path,
        remote_workspace_base=Path("/srv/builds/repo"),
        session_id="test-session",
    )

    payload = {}
    for line in session_workspace.shell_lines(workspace).splitlines():
        key, _, value = line.partition("=")
        payload[key] = json.loads(value)

    assert payload["LV3_SESSION_ID"] == "test-session"
    assert payload["LV3_SESSION_SLUG"] == "test-session"
    assert payload["LV3_REMOTE_WORKSPACE_ROOT"] == "/srv/builds/repo/.lv3-session-workspaces/test-session/repo"
