import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTION_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform"
BRIDGE_ROLE_ROOT = COLLECTION_ROOT / "roles" / "artifact_cache_ghcr_reader_bridge"
RENDERER_ROLE_ROOT = COLLECTION_ROOT / "roles" / "artifact_cache_ghcr_secret_renderer"
BRIDGE_SCRIPT_PATH = BRIDGE_ROLE_ROOT / "templates" / "artifact-cache-ghcr-reader-bridge.py.j2"
RENDERER_SCRIPT_PATH = RENDERER_ROLE_ROOT / "templates" / "artifact-cache-ghcr-secret-renderer.py.j2"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_renderer_contract() -> dict:
    return {
        "managed-by": "test",
        "schema_version": 1,
        "bridge": {
            "host": "10.10.10.20",
            "port": 22,
            "user": "artifact-cache-ghcr-reader",
            "private_key": "/etc/artifact-cache/ghcr-proxy-renderer/bridge-id_ed25519",
            "known_hosts": "/etc/artifact-cache/ghcr-proxy-renderer/bridge-known_hosts",
        },
        "vault": {
            "url": "https://fleet-secrets.0exec.com",
            "secret_name": "artifact_cache_ghcr_proxy_config",
        },
        "output": {
            "parent_dirs": ["/etc/artifact-cache", "/etc/artifact-cache/ghcr-proxy"],
            "path": "/etc/artifact-cache/ghcr-proxy/config.yml",
            "receipt": "/var/lib/artifact-cache/ghcr-proxy-renderer/last-render.json",
        },
    }


def _valid_distribution_config() -> dict:
    return {
        "version": "0.1",
        "log": {"level": "warn"},
        "storage": {
            "filesystem": {"rootdirectory": "/var/lib/registry"},
            "delete": {"enabled": True},
        },
        "http": {"addr": "0.0.0.0:5000"},
        "proxy": {
            "remoteurl": "https://ghcr.io",
            "username": "cache-only-reader",
            "password": "test-package-reader-token",
        },
    }


def test_dockerhost_bridge_is_forced_to_one_reader_and_one_source() -> None:
    defaults = yaml.safe_load((BRIDGE_ROLE_ROOT / "defaults" / "main.yml").read_text())
    tasks = yaml.safe_load((BRIDGE_ROLE_ROOT / "tasks" / "main.yml").read_text())
    authorized_keys = (BRIDGE_ROLE_ROOT / "templates" / "authorized_keys.j2").read_text()
    sudoers = (BRIDGE_ROLE_ROOT / "templates" / "sudoers.j2").read_text()
    sshd = (BRIDGE_ROLE_ROOT / "templates" / "sshd-artifact-cache-ghcr-reader.conf.j2").read_text()

    assert (
        defaults["artifact_cache_ghcr_reader_bridge_allowed_source"] == "{{ hostvars['artifact-cache'].ansible_host }}"
    )
    assert defaults["artifact_cache_ghcr_reader_bridge_apikey_url"] == "http://127.0.0.1:18021"
    assert defaults["artifact_cache_ghcr_reader_bridge_reader_principal"] == "artifact-cache-ghcr-config-renderer"
    assert defaults["artifact_cache_ghcr_reader_bridge_reader_ttl_seconds"] == 300
    assert defaults["artifact_cache_ghcr_reader_bridge_reader_use_limit"] == 1

    checks = tasks[0]["ansible.builtin.assert"]["that"]
    assert "inventory_hostname == 'docker-runtime'" in checks
    assert "artifact_cache_ghcr_reader_bridge_allowed_source == hostvars['artifact-cache'].ansible_host" in checks
    assert any("authorized_public_key is match" in item for item in checks)
    assert "artifact_cache_ghcr_reader_bridge_reader_scope == 'infra-privileged'" in checks
    assert "artifact_cache_ghcr_reader_bridge_reader_use_limit | int == 1" in checks

    for restriction in (
        "restrict",
        "no-port-forwarding",
        "no-agent-forwarding",
        "no-X11-forwarding",
        "no-pty",
        "no-user-rc",
    ):
        assert restriction in authorized_keys
    assert 'from="{{ artifact_cache_ghcr_reader_bridge_allowed_source }}"' in authorized_keys
    assert 'command="/usr/bin/sudo -n {{ artifact_cache_ghcr_reader_bridge_binary_path }} reader"' in authorized_keys
    assert "*" not in sudoers
    assert sudoers.rstrip().endswith(" reader")
    assert "Match User {{ artifact_cache_ghcr_reader_bridge_user }}" in sshd
    assert "    PermitUserEnvironment " not in sshd
    assert "restrict" in authorized_keys
    assert "AllowTcpForwarding no" in sshd
    assert sshd.rstrip().endswith("Match all")


def test_bridge_reader_contract_cannot_change_its_authority_or_endpoint() -> None:
    bridge = _load_module("artifact_cache_ghcr_reader_bridge", BRIDGE_SCRIPT_PATH)
    contract = {
        "managed-by": "test",
        "schema_version": 1,
        "admin_token_file": "/opt/_shared/apikey-admin.env",
        "apikey_url": "http://127.0.0.1:18021",
        "reader_principal": "artifact-cache-ghcr-config-renderer",
        "reader_scope": "infra-privileged",
        "reader_tier": "infra-privileged",
        "reader_ttl_seconds": 300,
        "reader_use_limit": 1,
    }

    assert bridge._validate_config(contract) == contract
    for field, value in (
        ("apikey_url", "https://example.invalid"),
        ("reader_principal", "other"),
        ("reader_ttl_seconds", 301),
        ("reader_use_limit", 2),
    ):
        changed = dict(contract, **{field: value})
        with pytest.raises(bridge.BridgeError):
            bridge._validate_config(changed)


def test_bridge_uses_one_reader_in_memory_and_always_attempts_revocation(monkeypatch) -> None:
    bridge = _load_module("artifact_cache_ghcr_reader_bridge_transaction", BRIDGE_SCRIPT_PATH)
    frames = iter((b"REQUEST\n", b"CONSUMED\n"))
    events = []

    monkeypatch.setattr(bridge.os, "geteuid", lambda: 0)
    monkeypatch.setattr(bridge, "_read_protocol_line", lambda: next(frames))
    monkeypatch.setattr(bridge, "_issue_reader", lambda: events.append("issue") or ("ak_" + "a" * 32))
    monkeypatch.setattr(bridge, "_revoke_reader", lambda key: events.append(("revoke", key)))

    bridge._reader_transaction({})
    assert events == ["issue", ("revoke", "ak_" + "a" * 32)]

    frames = iter((b"REQUEST\n", b"FAILED\n"))
    with pytest.raises(bridge.BridgeError):
        bridge._reader_transaction({})
    assert events[-2:] == ["issue", ("revoke", "ak_" + "a" * 32)]


def test_renderer_is_vm180_only_and_requires_pinned_root_only_transport() -> None:
    defaults = yaml.safe_load((RENDERER_ROLE_ROOT / "defaults" / "main.yml").read_text())
    tasks = yaml.safe_load((RENDERER_ROLE_ROOT / "tasks" / "main.yml").read_text())
    task_names = [task["name"] for task in tasks]

    assert (
        defaults["artifact_cache_ghcr_secret_renderer_bridge_host"] == "{{ hostvars['docker-runtime'].ansible_host }}"
    )
    assert defaults["artifact_cache_ghcr_secret_renderer_secret_name"] == "artifact_cache_ghcr_proxy_config"
    assert defaults["artifact_cache_ghcr_secret_renderer_output_path"] == "/etc/artifact-cache/ghcr-proxy/config.yml"
    assert defaults["artifact_cache_ghcr_secret_renderer_output_parent_dirs"] == [
        "/etc/artifact-cache",
        "/etc/artifact-cache/ghcr-proxy",
    ]
    assert "Require the existing root-only cache reader bridge transport key" in task_names
    assert "Render pinned Dockerhost host keys for the cache reader bridge" in task_names
    assert "Validate the root-only cache GHCR secret renderer contract" in task_names

    checks = tasks[0]["ansible.builtin.assert"]["that"]
    assert "inventory_hostname == 'artifact-cache'" in checks
    assert "artifact_cache_ghcr_secret_renderer_bridge_host == hostvars['docker-runtime'].ansible_host" in checks
    assert "artifact_cache_ghcr_secret_renderer_secret_name == 'artifact_cache_ghcr_proxy_config'" in checks
    assert "artifact_cache_ghcr_secret_renderer_output_path == '/etc/artifact-cache/ghcr-proxy/config.yml'" in checks

    key_assert = next(
        task for task in tasks if task["name"] == "Require the existing root-only cache reader bridge transport key"
    )
    key_checks = key_assert["ansible.builtin.assert"]["that"]
    assert "artifact_cache_ghcr_secret_renderer_transport_key_stat.stat.isreg" in key_checks
    assert "not artifact_cache_ghcr_secret_renderer_transport_key_stat.stat.islnk" in key_checks
    assert "artifact_cache_ghcr_secret_renderer_transport_key_stat.stat.mode == '0400'" in key_checks
    assert key_assert["no_log"] is True


def test_renderer_rejects_any_vault_record_output_or_transport_path_change() -> None:
    renderer = _load_module("artifact_cache_ghcr_secret_renderer_contract", RENDERER_SCRIPT_PATH)
    contract = _valid_renderer_contract()

    assert renderer._validate_config(contract) == contract
    changed = _valid_renderer_contract()
    changed["vault"]["secret_name"] = "other"
    with pytest.raises(renderer.RenderError):
        renderer._validate_config(changed)
    changed = _valid_renderer_contract()
    changed["output"]["path"] = "/tmp/config.yml"
    with pytest.raises(renderer.RenderError):
        renderer._validate_config(changed)
    changed = _valid_renderer_contract()
    changed["bridge"]["private_key"] = "/tmp/key"
    with pytest.raises(renderer.RenderError):
        renderer._validate_config(changed)


def test_renderer_accepts_only_the_complete_private_distribution_configuration() -> None:
    renderer = _load_module("artifact_cache_ghcr_secret_renderer_distribution", RENDERER_SCRIPT_PATH)
    payload = _valid_distribution_config()

    assert renderer._validate_distribution_config(__import__("json").dumps(payload)) == payload
    for mutate in (
        lambda value: value["http"].update(addr="0.0.0.0:5002"),
        lambda value: value["proxy"].update(remoteurl="https://example.invalid"),
        lambda value: value["storage"]["filesystem"].update(rootdirectory="/tmp/registry"),
        lambda value: value["proxy"].update(password="line\nbreak"),
        lambda value: value.update(extra=True),
    ):
        changed = _valid_distribution_config()
        mutate(changed)
        with pytest.raises(renderer.RenderError):
            renderer._validate_distribution_config(__import__("json").dumps(changed))


def test_renderer_uses_pinned_ssh_stdio_and_never_uses_environment_or_shell_transport() -> None:
    source = RENDERER_SCRIPT_PATH.read_text()

    assert '"StrictHostKeyChecking=yes"' in source
    assert '"GlobalKnownHostsFile=/dev/null"' in source
    assert '"IdentitiesOnly=yes"' in source
    assert 'process.stdin.write(b"REQUEST\\n")' in source
    assert 'b"CONSUMED\\n" if completed else b"FAILED\\n"' in source
    assert '"X-API-Key": reader_key' in source
    assert '"X-Expected-Scope": "infra-privileged"' in source
    assert '"X-Required-Tier": "infra-privileged"' in source
    assert "ProxyHandler({})" in source
    assert "NoRedirect" in source
    assert "shell=True" not in source
    assert "os.environ" not in source
    assert "sha256" not in source
    assert 'print("artifact-cache GHCR secret renderer failed"' in source


def test_delivery_playbook_runs_one_explicit_no_log_render_after_both_contracts_are_installed() -> None:
    playbook_path = COLLECTION_ROOT / "playbooks" / "artifact-cache-ghcr-secret-renderer.yml"
    plays = yaml.safe_load(playbook_path.read_text())

    assert [play["hosts"] for play in plays] == ["docker-runtime", "artifact-cache"]
    assert plays[0]["roles"] == [{"role": "lv3.platform.artifact_cache_ghcr_reader_bridge"}]
    assert plays[1]["roles"] == [{"role": "lv3.platform.artifact_cache_ghcr_secret_renderer"}]
    render = plays[1]["post_tasks"][0]
    assert render["no_log"] is True
    assert render["ansible.builtin.command"]["argv"] == [
        "{{ artifact_cache_ghcr_secret_renderer_binary_path }}",
        "render",
    ]
