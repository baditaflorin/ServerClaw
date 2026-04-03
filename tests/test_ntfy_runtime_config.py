from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ntfy_topic_registry_declares_governed_and_legacy_topics() -> None:
    registry = (REPO_ROOT / "config" / "ntfy" / "topics.yaml").read_text(encoding="utf-8")

    assert "platform-monitoring-critical:" in registry
    assert "platform-security-warn:" in registry
    assert "platform-backup-critical:" in registry
    assert "platform-ansible-critical:" in registry
    assert "platform-ci-critical:" in registry
    assert "platform-watchdog-critical:" in registry
    assert "platform-slo-warn:" in registry
    assert "platform-alerts:" in registry
    assert "platform-alerts-sbom-verify:" in registry


def test_ntfy_config_renders_governed_auth_line_payloads() -> None:
    config = (REPO_ROOT / "config" / "ntfy" / "server.yml").read_text(encoding="utf-8")

    assert "enable-login: true" in config
    assert "enable-signup: false" in config
    assert "auth-users: {{ ntfy_runtime_auth_user_lines | to_json }}" in config
    assert "auth-tokens: {{ ntfy_runtime_auth_token_lines | to_json }}" in config
    assert "auth-access: {{ ntfy_runtime_auth_access_lines | to_json }}" in config


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
    assert "Ensure Docker bridge networking chains are ready before ntfy startup" in tasks
    assert "Unable to enable DNAT rule" in tasks
    assert "Retry ntfy startup after Docker bridge-chain recovery" in tasks
    assert "Inspect current ntfy container port bindings" in tasks
    assert "Detect ntfy host port binding drift" in tasks
    assert "Recreate ntfy stack when host port binding drifts" in tasks
    assert "HostConfig.PortBindings" in tasks
    assert "Recreate ntfy stack when mounted config drifts" in tasks
    assert "Flush ntfy restart handlers before verification" in tasks
    assert "^tk_[a-z0-9]{29}$" in tasks
    assert "openssl rand -hex 24" not in tasks

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
