from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import container_image_policy as policy  # noqa: E402


def test_split_image_reference_supports_generic_registry_hosts() -> None:
    assert policy.split_image_reference("artifacts.plane.so/makeplane/plane-backend") == (
        "artifacts.plane.so",
        "makeplane/plane-backend",
    )


def test_fetch_bearer_token_returns_none_for_generic_registry() -> None:
    assert policy.fetch_bearer_token("artifacts.plane.so", "makeplane/plane-backend") is None
