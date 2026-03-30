from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ntfy_config_authorizes_sbom_verification_topic() -> None:
    config = (REPO_ROOT / "config" / "ntfy" / "server.yml").read_text(encoding="utf-8")

    assert 'platform-alerts:rw' in config
    assert 'platform-alerts-sbom-verify:rw' in config


def test_ntfy_runtime_restarts_when_config_changes() -> None:
    tasks = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "ntfy_runtime"
        / "tasks"
        / "main.yml"
    ).read_text(encoding="utf-8")

    assert "Render ntfy server config" in tasks
    assert "notify: Restart ntfy stack" in tasks
    assert "Recreate ntfy stack when mounted config drifts" in tasks
    assert "Flush ntfy restart handlers before verification" in tasks

    handlers = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "ntfy_runtime"
        / "handlers"
        / "main.yml"
    ).read_text(encoding="utf-8")

    assert "--force-recreate" in handlers
