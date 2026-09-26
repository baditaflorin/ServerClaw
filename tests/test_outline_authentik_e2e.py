from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import outline_authentik_e2e


def test_normalize_base_url_requires_plain_https_origin() -> None:
    assert outline_authentik_e2e.normalize_base_url("https://wiki.example.com/") == "https://wiki.example.com"

    with pytest.raises(outline_authentik_e2e.VerificationError, match="absolute HTTPS"):
        outline_authentik_e2e.normalize_base_url("http://wiki.example.com")
    with pytest.raises(outline_authentik_e2e.VerificationError, match="must not contain"):
        outline_authentik_e2e.normalize_base_url("https://wiki.example.com/auth/oidc")


def test_auth_info_requires_a_successful_outline_session() -> None:
    outline_authentik_e2e.verify_auth_info(200, {"data": {"user": {}}})

    with pytest.raises(outline_authentik_e2e.VerificationError, match="authenticated browser session"):
        outline_authentik_e2e.verify_auth_info(401, {"ok": False})


def test_realtime_contract_requires_engine_io_open_packet() -> None:
    outline_authentik_e2e.verify_realtime_result({"engine_open_packet": True})

    with pytest.raises(outline_authentik_e2e.VerificationError, match=r"Engine\.IO handshake"):
        outline_authentik_e2e.verify_realtime_result({"engine_open_packet": False})
