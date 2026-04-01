import base64
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import livekit_tool  # noqa: E402


def _decode_claims(token: str) -> dict[str, object]:
    payload = token.split(".")[1]
    padded = payload + "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


def test_build_admin_token_includes_room_management_grants() -> None:
    token = livekit_tool.build_token(
        api_key="API123",
        api_secret="secret456",
        claims=livekit_tool.build_admin_claims(api_key="API123", identity="agent-admin", ttl_seconds=300),
    )
    claims = _decode_claims(token)

    assert claims["iss"] == "API123"
    assert claims["sub"] == "agent-admin"
    assert claims["video"] == {
        "roomAdmin": True,
        "roomCreate": True,
        "roomList": True,
    }


def test_build_participant_token_includes_room_join_claims() -> None:
    token = livekit_tool.build_token(
        api_key="API123",
        api_secret="secret456",
        claims=livekit_tool.build_participant_claims(
            api_key="API123",
            identity="voice-user",
            room="room-123",
            ttl_seconds=120,
            can_publish=True,
            can_subscribe=False,
            metadata="session-42",
        ),
    )
    claims = _decode_claims(token)

    assert claims["sub"] == "voice-user"
    assert claims["metadata"] == "session-42"
    assert claims["video"] == {
        "canPublish": True,
        "canSubscribe": False,
        "room": "room-123",
        "roomJoin": True,
    }


def test_resolve_credentials_reads_runtime_env_file(tmp_path: Path) -> None:
    env_path = tmp_path / "runtime.env"
    env_path.write_text(
        "LIVEKIT_API_KEY=APIexample\nLIVEKIT_API_SECRET=supersecret\nLIVEKIT_KEYS=ignored: value\n",
        encoding="utf-8",
    )

    class Args:
        runtime_env_file = str(env_path)
        api_key = None
        api_secret = None
        api_key_file = None
        api_secret_file = None

    api_key, api_secret = livekit_tool.resolve_credentials(Args())
    assert api_key == "APIexample"
    assert api_secret == "supersecret"
